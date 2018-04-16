#!/usr/bin/env python
# -*- coding=utf-8 -*-
import uuid
import os
import json
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import permission_required
from OMBA.models import Server_Assets
from OMBA.data.DsRedisOps import DsRedis
from OMBA.data.DsMySQL import AnsibleRecord
from OMBA.utils.ansible_api_v2 import ANSRunner
from django.contrib.auth.models import User, Group
from OMBA.models import (
    Ansible_Playbook,
    Ansible_Playbook_Number,
    Log_Ansible_Model,
    Log_Ansible_Playbook,
    Ansible_CallBack_Model_Result,
    Service_Assets,
    Ansible_CallBack_PlayBook_Result,
    Assets,
    Ansible_Script,
    Project_Assets
)
from OMBA.utils.logger import logger


@login_required()
@permission_required('OMBA.can_read_ansible_model', login_url='/noperm/')
def apps_model(request):
    if request.method == "GET":
        projectList = Project_Assets.objects.all()
        serverList = Server_Assets.objects.all()
        groupList = Group.objects.all()
        serviceList = Service_Assets.objects.all()
        return render(
            request,
            'apps/apps_model.html',
            {
                "user": request.user,
                "ans_uuid": uuid.uuid4(),
                "serverList": serverList,
                "groupList": groupList,
                "serviceList": serviceList,
                "projectList": projectList
            }
        )
    elif request.method == "POST" and request.user.has_perm('OMBA.can_exec_ansible_model'):
        resource = []
        sList = []
        if request.POST.get('server_model') in ['service', 'group', 'custom']:
            if request.POST.get('server_model') == 'custom':
                serverList = request.POST.getlist('ansible_server')
                for server in serverList:
                    server_assets = Server_Assets.objects.get(id=server)
                    sList.append(server_assets.ip)
                    if server_assets.keyfile == 1:
                        resource.append(
                            {
                                "hostname": server_assets.ip,
                                "port": int(server_assets.port),
                                "username": server_assets.username
                            }
                        )
                    else:
                        resource.append(
                            {
                                "hostname": server_assets.ip,
                                "port": int(server_assets.port),
                                "username": server_assets.username,
                                "password": server_assets.passwd
                            }
                        )
            elif request.POST.get('server_model') == 'group':
                serverList = Assets.objects.filter(group=request.POST.get('ansible_group'), assets_type__in=["server", "vmser"])
                for server in serverList:
                    sList.append(server.server_assets.ip)
                    if server.server_assets.keyfile == 1:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username
                            }
                        )
                    else:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username,
                                "password": server.server_assets.passwd
                            }
                        )
            elif request.POST.get('server_model') == 'service':
                serverList = Assets.objects.filter(business=request.POST.get('ansible_service'), assets_type__in=["server", "vmser"])
                for server in serverList:
                    sList.append(server.server_assets.ip)
                    if server.server_assets.keyfile == 1:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username
                            }
                        )
                    else:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username,
                                "password": server.server_assets.passwd
                            }
                        )
            if len(request.POST.get('custom_model')) > 0:
                model_name = request.POST.get('custom_model')
            else:
                model_name = request.POST.get('ansible_model', None)
            if len(sList) > 0:
                redisKey = request.POST.get('ans_uuid')
                logId = AnsibleRecord.Model.insert(
                    user=str(request.user),
                    ans_model=model_name,
                    ans_server=','.join(sList),
                    ans_args=request.POST.get('ansible_args', None)
                )
                DsRedis.OpsAnsibleModel.delete(redisKey)
                DsRedis.OpsAnsibleModel.lpush(
                    redisKey,
                    "[Start] Ansible Model: {model}  ARGS:{args}".format(
                        model=model_name,
                        args=request.POST.get('ansible_args', "None")
                    )
                )
                if request.POST.get('ansible_debug') == 'on':
                    ANS = ANSRunner(resource, redisKey, logId, verbosity=4)
                else:
                    ANS = ANSRunner(resource, redisKey, logId)
                ANS.run_model(
                    host_list=sList,
                    module_name=model_name,
                    module_args=request.POST.get('ansible_args', "")
                )
                DsRedis.OpsAnsibleModel.lpush(redisKey, "[Done] Ansible Done.")
                return JsonResponse(
                    {
                        'msg': "操作成功",
                        "code": 200,
                        'data': []
                    }
                )
            else:
                return JsonResponse({'msg': "操作失败，未选择主机或者该分组没有成员", "code": 500, 'data': []})
        else:
            return JsonResponse({'msg': "操作失败，不支持的操作类型", "code": 500, 'data': []})


@login_required()
def ansible_run(request):
    if request.method == "POST":
        redisKey = request.POST.get('ans_uuid')
        msg = DsRedis.OpsAnsibleModel.rpop(redisKey)
        if msg:
            return JsonResponse(
                {
                    'msg': msg,
                    "code": 200,
                    'data': []
                }
            )
        else:
            return JsonResponse(
                {
                    'msg': None,
                    "code": 200,
                    'data': []
                }
            )


@login_required()
@permission_required('OMBA.can_add_ansible_playbook', login_url='/noperm/')
def apps_upload(request):
    if request.method == "GET":
        serverList = Server_Assets.objects.all()
        projectList = Project_Assets.objects.all()
        groupList = Group.objects.all()
        userList = User.objects.all()
        serviceList = Service_Assets.objects.all()
        return render(
            request,
            'app/apps_playbook_upload.html',
            {
                "user": request.user,
                "userList": userList,
                "serverList": serverList,
                "groupList": groupList,
                "serviceList": serviceList,
                "projectList": projectList
            },
        )
    elif request.method == "POST":
        sList = []
        if request.POST.get('server_model') in ['service', 'group', 'custom']:
            if request.POST.get('server_model') == 'custom':
                for sid in request.POST.getlist('playbook_server'):
                    server = Service_Assets.objects.get(id=sid)
                    sList.append(server.ip)
                playbook_server_value = None
            elif request.POST.get('server_model') == 'group':
                serverList = Assets.objects.filter(group=request.POST.get('ansible_group'))
                sList = [s.server_assets.ip for s in serverList]
                playbook_server_value = request.POST.get('ansible_group')
            elif request.POST.get('server_model') == 'service':
                serverList = Assets.objects.filter(business=request.POST.get('ansible_service'))
                sList = [s.server_assets.ip for s in serverList]
                playbook_server_value = request.POST.get('ansible_service')
        try:
            playbook = Ansible_Playbook.objects.create(
                playbook_name=request.POST.get('playbook_name'),
                playbook_desc=request.POST.get('playbook_desc'),
                playbook_vars=request.POST.get('playbook_vars'),
                playbook_uuid=uuid.uuid4(),
                playbook_file=request.FILES.get('playbook_file'),
                playbook_server_model=request.POST.get('server_model', 'custom'),
                playbook_server_value=playbook_server_value,
                playbook_auth_group=request.POST.get('playbook_auth_group', 0),
                playbook_auth_user=request.POST.get('playbook_auth_user', 0),
                playbook_type=0,
            )
        except Exception, ex:
            logger.error(msg="添加playbook失败: {ex}".format(ex=str(ex)))
            return render(
                request,
                'apps/apps_playbook_upload.html',
                {
                    "user": request.user,
                    "errorInfo": "剧本添加错误：%s" % str(ex)
                },
            )
        for sip in sList:
            try:
                Ansible_Playbook_Number.objects.create(
                    playbook=playbook,
                    playbook_server=sip
                )
            except Exception, ex:
                logger.error(msg="添加playbook目标主机失败: {ex}".format(ex=str(ex)))
                playbook.delete()
                return render(
                    request,
                    'apps/apps_playbook_upload.html',
                    {
                        "user": request.user,
                        "errorInfo": "目标服务器信息添加错误：%s" % str(ex)
                    },
                )
        # 操作日志异步记录
        AnsibleRecord.PlayBook.insert(
            user=str(request.user),
            ans_id=playbook.id,
            ans_name=playbook.playbook_name,
            ans_content="添加Ansible剧本",
            ans_server=','.join(sList)
        )
        return HttpResponseRedirect('apps/playbook/upload/')


@login_required()
@permission_required('OpsManage.can_add_ansible_playbook', login_url='/noperm/')
def apps_online(request):
    if request.method == "GET":
        serverList = Server_Assets.objects.all()
        groupList = Group.objects.all()
        userList = User.objects.all()
        serviceList = Service_Assets.objects.all()
        projectList = Project_Assets.objects.all()
        return render(
            request,
            'apps/apps_playbook_online.html',
            {
                "user": request.user,
                "userList": userList,
                "serverList": serverList,
                "groupList": groupList,
                "serviceList": serviceList,
                "projectList": projectList
            },
        )
    elif request.method == "POST":
        sList = []
        playbook_server_value = None
        if request.POST.get('server_model') in ['service', 'group', 'custom']:
            if request.POST.get('server_model') == 'custom':
                for sid in request.POST.getlist('playbook_server[]'):
                    server = Server_Assets.objects.get(id=sid)
                    sList.append(server.ip)
                playbook_server_value = None
            elif request.POST.get('server_model') == 'group':
                serverList = Assets.objects.filter(group=request.POST.get('ansible_group'))
                sList = [s.server_assets.ip for s in serverList]
                playbook_server_value = request.POST.get('ansible_group')
            elif request.POST.get('server_model') == 'service':
                serverList = Assets.objects.filter(business=request.POST.get('ansible_service'))
                sList = [s.server_assets.ip for s in serverList]
                playbook_server_value = request.POST.get('ansible_service')
        fileName = 'playbook/online-{ram}.yaml'.format(ram=uuid.uuid4().hex[0:8])
        filePath = os.getcwd() + '/upload/' + fileName
        if request.POST.get('playbook_content'):
            if os.path.isdir(os.path.dirname(filePath)) is not True:
                os.makedirs(os.path.dirname(filePath))  # 判断文件存放的目录是否存在，不存在就创建
            with open(filePath, 'w') as f:
                f.write(request.POST.get('playbook_content'))
        else:
            return JsonResponse(
                {
                    'msg': "文件内容不能为空",
                    "code": 500,
                    'data': []
                }
            )
        try:
            playbook = Ansible_Playbook.objects.create(
                playbook_name=request.POST.get('playbook_name'),
                playbook_desc=request.POST.get('playbook_desc'),
                playbook_vars=request.POST.get('playbook_vars'),
                playbook_uuid=uuid.uuid4(),
                playbook_file=fileName,
                playbook_server_model=request.POST.get('server_model', 'custom'),
                playbook_server_value=playbook_server_value,
                playbook_auth_group=request.POST.get('playbook_auth_group', 0),
                playbook_auth_user=request.POST.get('playbook_auth_user', 0),
                playbook_type=1
            )
        except Exception, ex:
            logger.error(msg="添加在线playbook失败: {ex}".format(ex=str(ex)))
            return JsonResponse(
                {
                    'msg': str(ex),
                    "code": 500,
                    'data': []
                }
            )
        for sip in sList:
            try:
                Ansible_Playbook_Number.objects.create(
                    playbook=playbook,
                    playbook_server=sip
                )
            except Exception, ex:
                playbook.delete()
                logger.error(msg="添加在线playbook目标失败: {ex}".format(ex=str(ex)))
        # 操作日志异步记录
        AnsibleRecord.PlayBook.insert(
            user=str(request.user),
            ans_id=playbook.id,
            ans_name=playbook.playbook_name,
            ans_content="添加Ansible剧本",
            ans_server=','.join(sList)
        )
        return JsonResponse(
            {
                'msg': None,
                "code": 200,
                'data': []
            }
        )


@login_required()
@permission_required('OpsManage.can_read_ansible_playbook', login_url='/noperm/')
def apps_list(request):
    if request.method == "GET":
        # 获取已登录用户的user id跟group id
        uid = User.objects.get(username=request.user).id
        gList = []
        for group in User.objects.get(username=request.user).groups.values():
            gList.append(group.get('id'))
        # 获取剧本数据列表
        playbookList = Ansible_Playbook.objects.all()
        for ds in playbookList:
            ds.ansible_playbook_number = Ansible_Playbook_Number.objects.filter(playbook=ds)
            # 如果用户在授权组或者是授权用户，设置runid等于项目id
            if ds.playbook_auth_group in gList or ds.playbook_auth_user == uid:
                ds.runid = ds.id
            # 如果剧本没有授权默认所有用户都可以使用
            elif ds.playbook_auth_group == 0 and ds.playbook_auth_user == 0:
                ds.runid = ds.id
        return render(
            request,
            'apps/apps_list.html',
            {
                "user": request.user,
                "playbookList": playbookList,
            }
        )


@login_required()
@permission_required('OpsManage.can_add_ansible_playbook', login_url='/noperm/')
def apps_playbook_file(request, pid):
    try:
        playbook = Ansible_Playbook.objects.get(id=pid)
    except:
        return JsonResponse(
            {
                'msg': "剧本不存在，可能已经被删除.",
                "code": 200,
                'data': []
            }
        )
    if request.method == "POST":
        playbook_file = os.getcwd() + '/upload/' + str(playbook.playbook_file)
        if os.path.exists(playbook_file):
            content = ''
            with open(playbook_file, "r") as f:
                for line in f.readlines():
                    content = content + line
            return JsonResponse(
                {
                    'msg': "剧本获取成功",
                    "code": 200,
                    'data': content
                }
            )
        else:
            return JsonResponse(
                {
                    'msg': "剧本不存在，可能已经被删除.",
                    "code": 500,
                    'data': []
                }
            )


@login_required()
@permission_required('OpsManage.can_read_ansible_playbook', login_url='/noperm/')
def apps_playbook_run(request, pid):
    try:
        playbook = Ansible_Playbook.objects.get(id=pid)
        numberList = Ansible_Playbook_Number.objects.filter(playbook=playbook)
        if numberList:
            serverList = []
        else:
            serverList = Server_Assets.objects.all()
    except:
        return render(
            request,
            'apps/apps_playbook.html',
            {
                "user": request.user,
                "ans_uuid": playbook.playbook_uuid,
                "errorInfo": "剧本不存在，可能已经被删除."
            },
        )
    if request.method == "GET":
        return render(
            request,
            'apps/apps_playbook.html',
            {
                "user": request.user,
                "playbook": playbook,
                "serverList": serverList,
                "numberList": numberList
            },
        )
    elif request.method == "POST" and request.user.has_perm('OpsManage.can_exec_ansible_playbook'):
        if DsRedis.OpsAnsiblePlayBookLock.get(redisKey=playbook.playbook_uuid + '-locked') is None:  # 判断剧本是否有人在执行
            # 加上剧本执行锁
            DsRedis.OpsAnsiblePlayBookLock.set(redisKey=playbook.playbook_uuid + '-locked', value=request.user)
            # 删除旧的执行消息
            DsRedis.OpsAnsiblePlayBook.delete(playbook.playbook_uuid)
            playbook_file = os.getcwd() + '/upload/' + str(playbook.playbook_file)
            sList = []
            resource = []
            if numberList:
                serverList = [s.playbook_server for s in numberList]
            else:
                serverList = request.POST.getlist('playbook_server')
            for server in serverList:
                server_assets = Server_Assets.objects.get(ip=server)
                sList.append(server_assets.ip)
                if server_assets.keyfile == 1:
                    resource.append(
                        {
                            "hostname": server_assets.ip,
                            "port": int(server_assets.port),
                            "username": server_assets.username
                        }
                    )
                else:
                    resource.append(
                        {
                            "hostname": server_assets.ip,
                            "port": int(server_assets.port),
                            "username": server_assets.username,
                            "password": server_assets.passwd
                        }
                    )
            if playbook.playbook_vars:
                playbook_vars = playbook.playbook_vars
            else:
                playbook_vars = request.POST.get('playbook_vars')
            try:
                if len(playbook_vars) == 0:
                    playbook_vars = dict()
                else:
                    playbook_vars = json.loads(playbook_vars)
                playbook_vars['host'] = sList
            except Exception, e:
                DsRedis.OpsAnsiblePlayBookLock.delete(redisKey=playbook.playbook_uuid + '-locked')
                return JsonResponse(
                    {
                        'msg': "剧本外部变量不是Json格式",
                        "code": 500,
                        'data': []
                    }
                )
            logId = AnsibleRecord.PlayBook.insert(
                user=str(request.user),
                ans_id=playbook.id,
                ans_name=playbook.playbook_name,
                ans_content="执行Ansible剧本",
                ans_server=','.join(sList)
            )
            # 执行 ansible playbook
            if request.POST.get('ansible_debug') == 'on':
                ANS = ANSRunner(
                    resource,
                    redisKey=playbook.playbook_uuid,
                    logId=logId,
                    verbosity=4
                )
            else:
                ANS = ANSRunner(
                    resource,
                    redisKey=playbook.playbook_uuid,
                    logId=logId
                )
            ANS.run_playbook(
                host_list=sList,
                playbook_path=playbook_file,
                extra_vars=playbook_vars
            )
            # 获取结果
            result = ANS.get_playbook_result()
            dataList = []
            statPer = {
                "unreachable": 0,
                "skipped": 0,
                "changed": 0,
                "ok": 0,
                "failed": 0
            }
            for k, v in result.get('status').items():
                v['host'] = k
                if v.get('failed') > 0 or v.get('unreachable') > 0:
                    v['result'] = 'Failed'
                else:
                    v['result'] = 'Succeed'
                dataList.append(v)
                statPer['unreachable'] = v['unreachable'] + statPer['unreachable']
                statPer['skipped'] = v['skipped'] + statPer['skipped']
                statPer['changed'] = v['changed'] + statPer['changed']
                statPer['failed'] = v['failed'] + statPer['failed']
                statPer['ok'] = v['ok'] + statPer['ok']
            DsRedis.OpsAnsiblePlayBook.lpush(playbook.playbook_uuid, "[Done] Ansible Done.")
            # 切换版本之后取消项目部署锁
            DsRedis.OpsAnsiblePlayBookLock.delete(redisKey=playbook.playbook_uuid + '-locked')
            # 操作日志异步记录
            # recordAnsiblePlaybook.delay(
            #     user=str(request.user),
            #     ans_id=playbook.id,
            #     ans_name=playbook.playbook_name,
            #     ans_content="执行Ansible剧本",
            #     uuid=playbook.playbook_uuid,
            #     ans_server=','.join(sList)
            # )
            return JsonResponse(
                {
                    'msg': "操作成功",
                    "code": 200,
                    'data': dataList,
                    "statPer": statPer
                }
            )
        else:
            return JsonResponse(
                {
                    'msg': "剧本执行失败，{user}正在执行该剧本".format(user=DsRedis.OpsAnsiblePlayBookLock.get(playbook.playbook_uuid + '-locked')),
                    "code": 500,
                    'data': []
                }
            )


@login_required()
@permission_required('OpsManage.can_change_ansible_playbook', login_url='/noperm/')
def apps_playbook_modf(request, pid):
    try:
        playbook = Ansible_Playbook.objects.get(id=pid)
        numberList = Ansible_Playbook_Number.objects.filter(playbook=playbook)
    except:
        return render(
            request,
            'apps/apps_playbook_modf.html',
            {
                "user": request.user,
                "errorInfo": "剧本不存在，可能已经被删除."
            },
        )
    if request.method == "GET":
        numberList = [s.playbook_server for s in numberList]
        serverList = Server_Assets.objects.all()
        projectList = Project_Assets.objects.all()
        for ds in serverList:
            if ds.ip in numberList:
                ds.count = 1
            else:
                ds.count = 0
        if playbook.playbook_type == 1:
            playbook_file = os.getcwd() + '/upload/' + str(playbook.playbook_file)
            if os.path.exists(playbook_file):
                content = ''
                with open(playbook_file,"r") as f:
                    for line in f.readlines():
                        content = content + line
                playbook.playbook_contents = content
        groupList = Group.objects.all()
        userList = User.objects.all()
        serviceList = Service_Assets.objects.all()
        try:
            project = Service_Assets.objects.get(id=playbook.playbook_server_value).project
            serviceList = Service_Assets.objects.filter(project=project)
        except:
            project = None
        return render(
            request,
            'apps/apps_playbook_modf.html',
            {
                "user": request.user,
                "userList": userList,
                "projectList": projectList,
                "playbook": playbook,
                "serverList": serverList,
                "project": project,
                "groupList": groupList,
                "serviceList": serviceList
            },
        )
    elif request.method == "POST":
        sList = []
        playbook_server_value = None
        if request.POST.get('server_model') in ['service', 'group', 'custom']:
            if request.POST.get('server_model') == 'custom':
                if playbook.playbook_type == 1:
                    serverList = request.POST.getlist('playbook_server[]')
                else:
                    serverList = request.POST.getlist('playbook_server')
                for sid in serverList:
                    server = Server_Assets.objects.get(id=sid)
                    sList.append(server.ip)
            elif request.POST.get('server_model') == 'group':
                serverList = Assets.objects.filter(group=request.POST.get('ansible_group'))
                sList = [s.server_assets.ip for s in serverList]
                playbook_server_value = request.POST.get('ansible_group')
            elif request.POST.get('server_model') == 'service':
                serverList = Assets.objects.filter(business=request.POST.get('ansible_service'))
                sList = [s.server_assets.ip for s in serverList]
                playbook_server_value = request.POST.get('ansible_service')
            if playbook.playbook_type == 1:
                playbook_file = os.getcwd() + '/upload/' + str(playbook.playbook_file)
                with open(playbook_file, 'w') as f:
                    f.write(request.POST.get('playbook_content'))
        try:
            Ansible_Playbook.objects.filter(id=pid).update(
                playbook_name=request.POST.get('playbook_name'),
                playbook_desc=request.POST.get('playbook_desc'),
                playbook_vars=request.POST.get('playbook_vars', None),
                playbook_server_model=request.POST.get('server_model', 'custom'),
                playbook_server_value=playbook_server_value,
                playbook_auth_group=request.POST.get('playbook_auth_group', 0),
                playbook_auth_user=request.POST.get('playbook_auth_user', 0),
            )
        except Exception, ex:
            logger.error(msg="修改playbook失败: {ex}".format(ex=str(ex)))
            return render(
                request,
                'apps/apps_playbook_modf.html',
                {
                    "user": request.user,
                    "errorInfo": "剧本添加错误：%s" % str(ex)
                },
            )
        if sList:
            tagret_server_list = [s.playbook_server for s in numberList]
            postServerList = []
            for sip in sList:
                try:
                    postServerList.append(sip)
                    if sip not in tagret_server_list:
                        Ansible_Playbook_Number.objects.create(
                            playbook=playbook,
                            playbook_server=sip
                        )
                except Exception, ex:
                    logger.error(msg="修改playbook目标服务器失败: {ex}".format(ex=str(ex)))
                    return render(
                        request,
                        'apps/apps_playbook_modf.html',
                        {
                            "user": request.user,
                            "errorInfo": "目标服务器信息修改错误：%s" % str(ex)
                        },
                    )
            # 清除目标主机
            delList = list(set(tagret_server_list).difference(set(postServerList)))
            for ip in delList:
                Ansible_Playbook_Number.objects.filter(playbook=playbook, playbook_server=ip).delete()
        else:
            for server in numberList:
                Ansible_Playbook_Number.objects.filter(playbook=playbook, playbook_server=server.playbook_server).delete()
        AnsibleRecord.PlayBook.insert(
            user=str(request.user),
            ans_id=playbook.id,
            ans_name=playbook.playbook_name,
            ans_content="修改Ansible剧本",
            ans_server=','.join(sList)
        )
        return HttpResponseRedirect('/apps/playbook/modf/{id}/'.format(id=pid))


@login_required()
@permission_required('OpsManage.can_change_ansible_playbook', login_url='/noperm/')
def apps_playbook_online_modf(request, pid):
    try:
        playbook = Ansible_Playbook.objects.get(id=pid)
        numberList = Ansible_Playbook_Number.objects.filter(playbook=playbook)
    except:
        return render(
            request,
            'apps/apps_playbook_modf.html',
            {
                "user": request.user,
                "errorInfo": "剧本不存在，可能已经被删除."
            },
        )
    if request.method == "POST":
        playbook_server_value = None
        sList = []
        if request.POST.get('server_model') in ['service', 'group', 'custom']:
            if request.POST.get('server_model') == 'custom':
                for sid in request.POST.getlist('playbook_server[]'):
                    server = Server_Assets.objects.get(id=sid)
                    sList.append(server.ip)
            elif request.POST.get('server_model') == 'group':
                serverList = Assets.objects.filter(group=request.POST.get('ansible_group'))
                sList = [s.server_assets.ip for s in serverList]
                playbook_server_value = request.POST.get('ansible_group')
            elif request.POST.get('server_model') == 'service':
                serverList = Assets.objects.filter(business=request.POST.get('ansible_service'))
                sList = [s.server_assets.ip for s in serverList]
                playbook_server_value = request.POST.get('ansible_service')
        if request.POST.get('playbook_content'):
            playbook_file = os.getcwd() + '/upload/' + str(playbook.playbook_file)
            with open(playbook_file, 'w') as f:
                f.write(request.POST.get('playbook_content'))
        else:
            return JsonResponse(
                {
                    'msg': "文件内容不能为空",
                    "code": 500,
                    'data': []
                }
            )
        try:
            Ansible_Playbook.objects.filter(id=pid).update(
                playbook_name=request.POST.get('playbook_name'),
                playbook_desc=request.POST.get('playbook_desc'),
                playbook_vars=request.POST.get('playbook_vars', None),
                playbook_server_model=request.POST.get('server_model', 'custom'),
                playbook_server_value=playbook_server_value,
                playbook_auth_group=request.POST.get('playbook_auth_group', 0),
                playbook_auth_user=request.POST.get('playbook_auth_user', 0),
            )
        except Exception, ex:
            logger.error(msg="修改playbook目标失败: {ex}".format(ex=str(ex)))
            return JsonResponse(
                {
                    'msg': str(ex),
                    "code": 500,
                    'data': []
                }
            )
        if sList:
            tagret_server_list = [s.playbook_server for s in numberList]
            postServerList = []
            for sip in sList:
                try:
                    postServerList.append(sip)
                    if sip not in tagret_server_list:
                        Ansible_Playbook_Number.objects.create(playbook=playbook, playbook_server=sip)
                except Exception, e:
                    return render(
                        request,
                        'apps/apps_playbook_modf.html',
                        {
                            "user": request.user,
                            "errorInfo": "目标服务器信息修改错误：%s" % str(e)
                        },
                    )
                    # 清除目标主机 -
            delList = list(set(tagret_server_list).difference(set(postServerList)))
            for ip in delList:
                Ansible_Playbook_Number.objects.filter(playbook=playbook, playbook_server=ip).delete()
        else:
            for server in numberList:
                Ansible_Playbook_Number.objects.filter(playbook=playbook, playbook_server=server.playbook_server).delete()
        AnsibleRecord.PlayBook.insert(
            user=str(request.user),
            ans_id=playbook.id,
            ans_name=playbook.playbook_name,
            ans_content="修改Ansible剧本",
            ans_server=','.join(sList)
        )
        return JsonResponse(
            {
                'msg': "更新成功",
                "code": 200,
                'data': []
            }
        )


@login_required(login_url='/login')
def ansible_log(request):
    if request.method == "GET":
        modelList = Log_Ansible_Model.objects.all().order_by('-id')[0:120]
        playbookList = Log_Ansible_Playbook.objects.all().order_by('-id')[0:120]
        return render(
            request,
            'apps/apps_log.html',
            {
                "user": request.user,
                "modelList": modelList,
                "playbookList": playbookList
            },
        )


@login_required(login_url='/login')
def ansible_log_view(request, model, id):
    if request.method == "POST":
        if model == 'model':
            try:
                result = ''
                logId = Log_Ansible_Model.objects.get(id=id)
                for ds in Ansible_CallBack_Model_Result.objects.filter(logId=logId):
                    result += ds.content
                    result += '\n'
            except Exception, ex:
                return JsonResponse(
                    {
                        'msg': "查看失败",
                        "code": 500,
                        'data': ex
                    }
                )
        elif model == 'playbook':
            try:
                result = ''
                logId = Log_Ansible_Playbook.objects.get(id=id)
                for ds in Ansible_CallBack_PlayBook_Result.objects.filter(logId=logId):
                    result += ds.content
                    result += '\n'
            except Exception, ex:
                return JsonResponse(
                    {
                        'msg': "查看失败",
                        "code": 500,
                        'data': ex
                    }
                )
        return JsonResponse(
            {
                'msg': "操作成功",
                "code": 200,
                'data': result
            }
        )


@login_required()
@permission_required('OpsManage.can_read_ansible_script', login_url='/noperm/')
def apps_script_online(request):
    if request.method == "GET":
        serverList = Server_Assets.objects.all()
        groupList = Group.objects.all()
        serviceList = Service_Assets.objects.all()
        projectList = Project_Assets.objects.all()
        return render(
            request,
            'apps/apps_script_online.html',
            {
                "user": request.user,
                "ans_uuid": uuid.uuid4(),
                "serverList": serverList,
                "groupList": groupList,
                "serviceList": serviceList,
                "projectList": projectList
            }
        )
    elif request.method == "POST" and request.user.has_perm('OpsManage.can_exec_ansible_script'):
        resource = []
        sList = []

        def saveScript(content, filePath):
            if os.path.isdir(os.path.dirname(filePath)) is not True:
                os.makedirs(os.path.dirname(filePath))  # 判断文件存放的目录是否存在，不存在就创建
            with open(filePath, 'w') as f:
                f.write(content)
            return filePath

        if request.POST.get('server_model') in ['service', 'group', 'custom']:
            if request.POST.get('server_model') == 'custom':
                serverList = request.POST.getlist('ansible_server[]')
                for server in serverList:
                    server_assets = Server_Assets.objects.get(id=server)
                    sList.append(server_assets.ip)
                    if server_assets.keyfile == 1:
                        resource.append(
                            {
                                "hostname": server_assets.ip,
                                "port": int(server_assets.port),
                                "username": server_assets.username
                            }
                        )
                    else:
                        resource.append(
                            {
                                "hostname": server_assets.ip,
                                "port": int(server_assets.port),
                                "username": server_assets.username,
                                "password": server_assets.passwd
                            }
                        )
            elif request.POST.get('server_model') == 'group':
                try:
                    serverList = Assets.objects.filter(group=request.POST.get('ansible_group', 0), assets_type__in=["server", "vmser"])
                except:
                    serverList = []
                for server in serverList:
                    try:
                        sList.append(server.server_assets.ip)
                    except Exception, ex:
                        print ex
                        continue
                    if server.server_assets.keyfile == 1:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username
                            }
                        )
                    else:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username,
                                "password": server.server_assets.passwd
                            }
                        )
            elif request.POST.get('server_model') == 'service':
                try:
                    serverList = Assets.objects.filter(business=int(request.POST.get('ansible_service', 0)), assets_type__in=["server", "vmser"])
                except:
                    serverList = []
                for server in serverList:
                    try:
                        sList.append(server.server_assets.ip)
                    except Exception, ex:
                        print ex
                        continue
                    if server.server_assets.keyfile == 1:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username
                            }
                        )
                    else:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username,
                                "password": server.server_assets.passwd
                            }
                        )

            if len(sList) > 0 and request.POST.get('type') == 'run' and request.POST.get('script_file'):
                filePath = saveScript(
                    content=request.POST.get('script_file'),
                    filePath='/tmp/script-{ram}'.format(ram=uuid.uuid4().hex[0:8])
                )
                redisKey = request.POST.get('ans_uuid')
                logId = AnsibleRecord.Model.insert(
                    user=str(request.user),
                    ans_model='script',
                    ans_server=','.join(sList),
                    ans_args=filePath
                )
                DsRedis.OpsAnsibleModel.delete(redisKey)
                DsRedis.OpsAnsibleModel.lpush(
                    redisKey,
                    "[Start] Ansible Model: {model} Script:{args}".format(model='script', args=filePath)
                )
                if request.POST.get('ansible_debug') == 'on':
                    ANS = ANSRunner(
                        resource,
                        redisKey,
                        logId,
                        verbosity=4
                    )
                else:
                    ANS = ANSRunner(
                        resource,
                        redisKey,
                        logId
                    )
                ANS.run_model(
                    host_list=sList,
                    module_name='script',
                    module_args=filePath
                )
                DsRedis.OpsAnsibleModel.lpush(redisKey, "[Done] Ansible Done.")
                try:
                    os.remove(filePath)
                except Exception, ex:
                    print ex
                return JsonResponse(
                    {
                        'msg': "操作成功",
                        "code": 200,
                        'data': []
                    }
                )
        if request.POST.get('type') == 'save' and request.POST.get('script_file'):
            fileName = '/upload/scripts/script-{ram}'.format(ram=uuid.uuid4().hex[0:8])
            filePath = os.getcwd() + fileName
            saveScript(content=request.POST.get('script_file'), filePath=filePath)
            try:
                service = int(request.POST.get('ansible_service'))
            except:
                service = None
            try:
                group = int(request.POST.get('ansible_group'))
            except:
                group = None
            try:
                Ansible_Script.objects.create(
                    script_name=request.POST.get('script_name'),
                    script_uuid=request.POST.get('ans_uuid'),
                    script_server=json.dumps(sList),
                    script_group=group,
                    script_file=fileName,
                    script_service=service,
                    script_type=request.POST.get('server_model')
                )
            except Exception, ex:
                logger.error(msg="保存脚本失败: {ex}".format(ex=str(ex)))
                return JsonResponse(
                    {
                        'msg': str(ex),
                        "code": 500,
                        'data': []
                    }
                )
            return JsonResponse(
                {
                    'msg': "保存成功",
                    "code": 200,
                    'data': []
                }
            )
        else:
            return JsonResponse(
                {
                    'msg': "操作失败，未选择主机或者脚本内容为空,或者所选分组该没有成员",
                    "code": 500,
                    'data': []
                }
            )


@login_required()
@permission_required('OpsManage.can_read_ansible_script', login_url='/noperm/')
def apps_script_list(request):
    if request.method == "GET":
        scriptList = Ansible_Script.objects.all()
        gList = []
        for group in User.objects.get(username=request.user).groups.values():
            gList.append(group.get('id'))
        for ds in scriptList:
            # 如果用户是超级管理员，设置runid等于项目id
            if request.user.is_superuser:
                ds.runid = ds.id
            # 如果用户在授权组或者是授权用户，设置runid等于项目id
            elif ds.script_group in gList:
                ds.runid = ds.id
            # 如果剧本没有授权默认所有用户都可以使用
            elif ds.script_group == 0:
                ds.runid = ds.id
            ds.script_server = json.loads(ds.script_server)
        return render(
            request,
            'apps/apps_script_list.html',
            {
                "user": request.user,
                "scriptList": scriptList
            }
        )


@login_required()
@permission_required('OpsManage.can_read_ansible_script', login_url='/noperm/')
def apps_script_file(request, pid):
    try:
        script = Ansible_Script.objects.get(id=pid)
    except:
        return JsonResponse(
            {
                'msg': "脚本不存在，可能已经被删除.",
                "code": 200,
                'data': []
            }
        )
    if request.method == "POST":
        script_file = os.getcwd() + str(script.script_file)
        if os.path.exists(script_file):
            content = ''
            with open(script_file, "r") as f:
                for line in f.readlines():
                    content = content + line
            return JsonResponse(
                {
                    'msg': "脚本获取成功",
                    "code": 200,
                    'data': content
                }
            )
        else:
            return JsonResponse(
                {
                    'msg': "脚本不存在，可能已经被删除.",
                    "code": 500,
                    'data': []
                }
            )
    elif request.method == "DELETE":
        try:
            script.delete()
        except Ansible_Script.DoesNotExist:
            return JsonResponse(
                {
                    'msg': "脚本不存在，可能已经被删除.",
                    "code": 500,
                    'data': []
                }
            )
        return JsonResponse(
            {
                'msg': "脚本删除成功",
                "code": 200,
                'data': []
            }
        )


@login_required()
@permission_required('OpsManage.can_read_ansible_script', login_url='/noperm/')
def apps_script_online_run(request, pid):
    try:
        script = Ansible_Script.objects.get(id=pid)
        numberList = json.loads(script.script_server)
    except:
        return render(
            request,
            'apps/apps_script_modf.html',
            {
                "user": request.user,
                "errorInfo": "剧本不存在，可能已经被删除."
            },
        )

    def saveScript(content, filePath):
        if os.path.isdir(os.path.dirname(filePath)) is not True:
            os.makedirs(os.path.dirname(filePath))  # 判断文件存放的目录是否存在，不存在就创建
        with open(filePath, 'w') as f:
            f.write(content)
        return filePath
    if request.method == "GET":
        projectList = Project_Assets.objects.all()
        serverList = Server_Assets.objects.all()
        for ds in serverList:
            if ds.ip in numberList:
                ds.count = 1
            else:
                ds.count = 0
        script_file = os.getcwd() + '/upload/' + str(script.script_file)
        if os.path.exists(script_file):
            content = ''
            with open(script_file, "r") as f:
                for line in f.readlines():
                    content = content + line
            script.script_contents = content
        groupList = Group.objects.all()
        userList = User.objects.all()
        serviceList = []
        try:
            project = Service_Assets.objects.get(id=script.script_service).project
            serviceList = Service_Assets.objects.filter(project=project)
        except:
            project = None
        return render(
            request,
            'apps/apps_script_modf.html',
            {
                "user": request.user,
                "userList": userList,
                "script": script,
                "serverList": serverList,
                "groupList": groupList,
                "serviceList": serviceList,
                "project": project,
                "projectList": projectList
            },
        )
    elif request.method == "POST"and request.user.has_perm('OpsManage.can_exec_ansible_script'):
        resource = []
        sList = []
        if request.POST.get('server_model') in ['service', 'group', 'custom']:
            if request.POST.get('server_model') == 'custom':
                serverList = request.POST.getlist('ansible_server[]')
                for server in serverList:
                    server_assets = Server_Assets.objects.get(id=server)
                    sList.append(server_assets.ip)
                    if server_assets.keyfile == 1:
                        resource.append(
                            {
                                "hostname": server_assets.ip,
                                "port": int(server_assets.port),
                                "username": server_assets.username
                            }
                        )
                    else:
                        resource.append(
                            {
                                "hostname": server_assets.ip,
                                "port": int(server_assets.port),
                                "username": server_assets.username,
                                "password": server_assets.passwd
                            }
                        )
            elif request.POST.get('server_model') == 'group':
                serverList = Assets.objects.filter(group=request.POST.get('ansible_group'), assets_type__in=["server", "vmser"])
                for server in serverList:
                    sList.append(server.server_assets.ip)
                    if server.server_assets.keyfile == 1:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username
                            }
                        )
                    else:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username,
                                "password": server.server_assets.passwd
                            }
                        )
            elif request.POST.get('server_model') == 'service':
                serverList = Assets.objects.filter(business=request.POST.get('ansible_service'), assets_type__in=["server", "vmser"])
                for server in serverList:
                    try:
                        sList.append(server.server_assets.ip)
                    except Exception, ex:
                        print ex
                        continue
                    if server.server_assets.keyfile == 1:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username
                            }
                        )
                    else:
                        resource.append(
                            {
                                "hostname": server.server_assets.ip,
                                "port": int(server.server_assets.port),
                                "username": server.server_assets.username,
                                "password": server.server_assets.passwd
                            }
                        )
        if request.POST.get('type') == 'save' and request.POST.get('script_file'):
            filePath = os.getcwd() + '/upload/' + str(script.script_file)
            saveScript(content=request.POST.get('script_file'), filePath=filePath)
            try:
                print request.POST.get('ansible_group', 0).replace(' ', '')
                Ansible_Script.objects.filter(id=pid).update(
                    script_server=json.dumps(sList),
                    script_group=request.POST.get('ansible_group', 0),
                    script_service=request.POST.get('ansible_service', 0),
                    script_type=request.POST.get('server_model')
                )
            except Exception, ex:
                return JsonResponse(
                    {
                        'msg': str(ex),
                        "code": 500,
                        'data': []
                    }
                )
            return JsonResponse(
                {
                    'msg': "保存成功",
                    "code": 200,
                    'data': []
                }
            )
        else:
            return JsonResponse(
                {
                    'msg': "操作失败，不支持的操作类型，或者您没有权限执行",
                    "code": 500,
                    'data': []
                }
            )
