#!/usr/bin/env python
# -*- coding=utf-8 -*-

import os, json, re
from collections import namedtuple
from ansible import constants
from ansible.parsing.dataloader import DataLoader
from ansible.vars import VariableManager
from ansible.inventory import Inventory, Host, Group
from ansible.playbook.play import Play
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.plugins.callback import CallbackBase
from ansible.executor.playbook_executor import PlaybookExecutor
from OMBA.data.DsRedisOps import DsRedis
from OMBA.data.DsMySQL import AnsibleSaveResult

class MyInventory(Inventory):
    """
    this is my ansible inventory object.
    """
    def __init__(self, resource, loader, variable_manager):
        """
        ansible inventory object
        :param resource: 一个列表字典，如
            {
                "group1": {
                    "hosts": [{"hostname": "10.0.0.0", "port": "22", "username": "test", "password": "pass"}, ...],
                    "vars": {"var1": value1, "var2": value2, ...}
                }
            }
            如果只传入1个列表，这默认该列表内的所有主机属于 my_group 组,比如
            [{"hostname": "10.0.0.0", "port": "22", "username": "test", "password": "pass"}, ...]
        :param loader:
        :param variable_manager:
        """
        self.resource = resource
        self.inventory = Inventory(loader=loader, variable_manager=variable_manager, host_list=[])
        self.dynamic_inventory()

    def add_dynamic_group(self, hosts, groupname, groupvars=None):
        """
        add hosts to a group
        :param hosts:
        :param groupname:
        :param groupvars:
        :return:
        """
        my_group = Group(name=groupname)

        # if group variables exists, add them to group
        if groupvars:
            for key, value in groupvars.iteritems():
                my_group.set_variable(key, value)

        # add hosts to group
        for host in hosts:
            # set connection variables
            hostname = host.get("hostname")
            hostip = host.get('ip', hostname)
            hostport = host.get("port")
            username = host.get("username")
            password = host.get("password")
            if username == 'root':
                keyfile = "/root/.ssh/id_rsa"
            else:
                keyfile = "/home/{user}/.ssh/id_rsa".format(user=username)
            ssh_key = host.get("ssh_key", keyfile)
            my_host = Host(name=hostname, port=hostport)
            my_host.set_variable('ansible_ssh_host', hostip)
            my_host.set_variable('ansible_ssh_port', hostport)
            my_host.set_variable('ansible_ssh_user', username)
            my_host.set_variable('ansible_ssh_pass', password)
            my_host.set_variable('ansible_ssh_private_key_file', ssh_key)

            # set other variables
            for key, value in host.iteritems():
                if key not in ["hostname", "port", "username", "password"]:
                    my_host.set_variable(key, value)

            # add to group
            my_group.add_host(my_host)
        self.inventory.add_group(my_group)

    def dynamic_inventory(self):
        """
        add hosts to inventory.
        :return:
        """
        if isinstance(self.resource, list):
            self.add_dynamic_group(self.resource, 'default_group')
        elif isinstance(self.resource, dict):
            for groupname, host_and_vars in self.resource.iteritems():
                self.add_dynamic_group(host_and_vars.get("hosts"), groupname, host_and_vars.get("vars"))

class ModelResultsCollector(CallbackBase):
    """
    ModelResultsCollector
    """
    def __init__(self, *args, **kwargs):
        super(ModelResultsCollector, self).__init__(*args, **kwargs)
        self.host_ok = {}
        self.host_unreachable = {}
        self.host_failed = {}

    def v2_runner_on_unreachable(self, result):
        self.host_unreachable[result._host.get_name()] = result

    def v2_runner_on_ok(self, result, *args, **kwargs):
        self.host_ok[result._host.get_name()] = result

    def v2_runner_on_failed(self, result, *args, **kwargs):
        self.host_failed[result._host.get_name()] = result

class ModelResultsCollectorToSave(CallbackBase):
    """
    ModelResultsCollectorToSave
    """
    def __init__(self, redisKey, logId, *args, **kwargs):
        super(ModelResultsCollectorToSave, self).__init__(*args, **kwargs)
        self.host_ok = {}
        self.host_unreachable = {}
        self.host_failed = {}
        self.redisKey = redisKey
        self.logId = logId

    def v2_runner_on_unreachable(self, result):
        for remove_key in ('changed', 'invocation'):
            if remove_key in result._result:
                del result._result[remove_key]
        data = "{host} | UNREACHABLE! => {stdout}".format(host=result._host.get_name, stdout=json.dumps(result._result, indent=4))
        DsRedis.OpsAnsibleModel.lpush(self.redisKey, data)
        if self.logId:AnsibleSaveResult.Model.insert(self.logId, data)

    def v2_runner_on_ok(self, result, *args, **kwargs):
        for remove_key in ('changed', 'invocation'):
            if remove_key in result._result:
                del result._result[remove_key]
        if result._result.has_key('rc') and result._result.has_key('stdout'):
            data = "{host} | SUCCESS | rc={rc} >> \n{stdout}".format(host=result._host.get_name(), rc=result._result.get('rc'), stdout=result._result.get('stdout'))
        else:
            data = "{host} | SUCCESS >> {stdout}".format(host=result._host.get_name(), stdout=json.dumps(result._result, indent=4))
        DsRedis.OpsAnsibleModel.lpush(self.redisKey, data)

    def v2_runner_on_failed(self, result, *args, **kwargs):
        for remove_key in ('changed', 'invocation'):
            if remove_key in result._result:
                del result._result[remove_key]
        if result._result.has_key('rc') and result._result.has_key('stdout'):
            data = "{host} | FAILED | rc={rc} >> \n{stdout}".format(host=result._host.get_name(), rc=result._result.get('rc'), stdout=result._result.get('stdout'))
        else:
            data = "{host} | FAILED! => {stdout}".format(host=result._host.get_name(), stdout=json.dumps(result._result, indent=4))
        DsRedis.OpsAnsibleModel.lpush(self.redisKey, data)
        if self.logId:AnsibleSaveResult.Model.insert(self.logId, data)

class PlayBookResultsCollectorToSave(CallbackBase):
    """
    PlayBookResultsCollectorToSave
    """
    CALLBACK_VERSION = 2.0
    def __init__(self, redisKey, logId, *args, **kwargs):
        super(PlayBookResultsCollectorToSave, self).__init__(*args, **kwargs)
        self.task_ok = {}
        self.task_skipped = {}
        self.task_failed = {}
        self.task_status = {}
        self.task_unreachable = {}
        self.task_changed = {}
        self.redisKey = redisKey
        self.logId = logId

    def v2_runner_on_unreachable(self, result):
        self.task_unreachable[result._host.get_name] = result._result
        msg = "fatal: [{host}]: UNREACHABLE! => {msg}\n".format(host=result._host.get_name(), msg=json.dumps(result._result))
        DsRedis.OpsAnsiblePlayBook.lpush(self.redisKey, msg)
        if self.logId:AnsibleSaveResult.PlayBook.insert(self.logId, msg)

    def v2_runner_on_changed(self, result):
        self.task_changed[result._host.get_name()] = result._result
        msg = "changed: [{host}]\n".format(host=result._host.get_name())
        DsRedis.OpsAnsiblePlayBook.lpush(self.redisKey, msg)
        if self.logId:AnsibleSaveResult.PlayBook.insert(self.logId, msg)

    def v2_runner_on_skipped(self, result):
        self.task_ok[result._host.get_name()] = result._result
        msg = "skipped: [{host}]\n".format(host=result._host.get_name())
        DsRedis.OpsAnsiblePlayBook.lpush(self.redisKey, msg)
        if self.logId:AnsibleSaveResult.PlayBook.insert(self.logId, msg)

    def v2_runner_on_play_start(self, play):
        name = play.get_name().strip()
        if not name:
            msg = u"PLAY"
        else:
            msg = u"PLAY [%s] " % name
        if len(msg) < 80:msg = msg + '*'*(79-len(msg))
        DsRedis.OpsAnsiblePlayBook.lpush(self.redisKey, msg)
        if self.logId:AnsibleSaveResult.PlayBook.insert(self.logId, msg)

    def _print_task_banner(self, task):
        msg = "\nTASK [%s] " % (task.get_name().strip())
        if len(msg) < 80:msg = msg + '*'*(80-len(msg))
        DsRedis.OpsAnsiblePlayBook.lpush(self.redisKey, msg)
        if self.logId:AnsibleSaveResult.PlayBook.insert(self.redisKey, msg)

    def v2_playbook_on_task_start(self, task, is_conditional):
        self._print_task_banner(task)

    def v2_playbook_on_cleanup_task_start(self, task):
        msg = "CLEANUP TASK [%s]" % task.get_name().strip()
        DsRedis.OpsAnsiblePlayBook.lpush(self.redisKey, msg)
        if self.logId:AnsibleSaveResult.PlayBook.insert(self.logId, msg)

    def v2_playbook_on_handler_task_start(self, task):
        msg = "RUNNING HANDLER [%s]" % task.get_name().strip()
        DsRedis.OpsAnsiblePlayBook.lpush(self.redisKey, msg)
        if self.logId:AnsibleSaveResult.PlayBook.insert(self.logId, msg)

    def v2_playbook_on_stats(self, stats):
        msg = "\nPLAY RECAP *******************************************************************"
        DsRedis.OpsAnsiblePlayBook.lpush(self.redisKey, msg)
        hosts = sorted(stats.processed.keys())
        for h in hosts:
            t = stats.summarize(h)
            self.task_status[h] = {
                "ok": t['ok'],
                "changed": t['changed'],
                "unreachable": t['unreachable'],
                "skipped": t['skipped'],
                "failed": t['failures']
            }
            msg = "{host}\t\t: ok={ok}\tchanged={changed}\tunreachable={unreachable}\tskipped={skipped}\tfailed={failed}".format(
                host=h,
                ok=t['ok'], changed=t['changed'],
                unreachable=t['unreachable'],
                skipped=t['skipped'], failed=t['failures']
            )
            DsRedis.OpsAnsiblePlayBook.lpush(self.redisKey, msg)
            if self.logId:AnsibleSaveResult.PlayBook.insert(self.logId, msg)

    def v2_runner_item_on_ok(self, result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if result._task.action in ('include', 'include_role'):
            return
        elif result._result.get('changed', False):
            msg = 'changed'
        else:
            msg = 'ok'
        if delegated_vars:
            msg += ": [%s -> %s]" % (result._host.get_name(), delegated_vars['ansible_host'])
        else:
            msg += ": [%s]" % result._host.get_name()
        msg += " => (item=%s)" % (json.dumps(self._get_item(result._result)))
        if (self._display.verbosity > 0 or '_ansible_verbose_always' in result._result) and not  '_ansible_verbose_override' in result._result:
            msg += " => %s" % json.dumps(result._result)
        DsRedis.OpsAnsiblePlayBook.lpush(self.redisKey, msg)
        if self.logId:AnsibleSaveResult.PlayBook.insert(self.logId, msg)

    def v2_runner_item_on_failed(self, result):
        task_name = result.task_name or result._task
