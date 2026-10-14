#!/usr/bin/env python3
"""
infra.py — Dựng và dọn hạ tầng AWS cho GĐ1 (Nội dung 4 của thuyết minh).

Hạ tầng gồm:
  - 2 security group : alb-sg (cho IP của bạn vào cổng 80),
                       web-sg (chỉ cho ALB vào cổng 80 của máy)
  - 1 launch template: "khuôn" để ASG đúc máy (AMI, loại máy, user-data)
  - 1 target group   : danh sách máy mà ALB chia request tới + health check
  - 1 ALB            : cửa vào duy nhất, chia request cho các máy khỏe
  - 1 Auto Scaling Group (ASG): giữ đúng số máy mong muốn (desired)

CÁCH CHẠY (từ thư mục gốc repo, KHÔNG cần sudo):
    python3 -m cloud.infra up          # dựng (ASG bắt đầu với 0 máy)
    python3 -m cloud.infra status      # xem trạng thái
    python3 -m cloud.infra scale 2     # đặt số máy mong muốn = 2 (thử tay)
    python3 -m cloud.infra lbtest 30   # gửi 30 request qua ALB, đếm theo máy
    python3 -m cloud.infra down        # dọn SẠCH mọi thứ (luôn chạy khi xong)

NGUYÊN TẮC AN TOÀN:
  - Mọi tài nguyên có tag Project=dt4n.
  - ASG tối đa 3 máy (config.HARD_MAX), kể cả khi gõ scale 10.
  - Máy KHÔNG có IP công khai; chỉ ALB nhận request từ ngoài, và chỉ từ IP của bạn.
  - `down` tìm tài nguyên theo TÊN, nên vẫn dọn được nếu mất file state.
"""

import argparse
import base64
import collections
import json
import sys
import time
import urllib.request

import boto3
from botocore.exceptions import ClientError

from cloud import config as C


# ===========================================================================
# PHẦN 0 — tiện ích chung
# ===========================================================================
def aws(service):
    """Tạo client boto3 cho đúng region. Key lấy từ ~/.aws hoặc biến môi trường."""
    return boto3.client(service, region_name=C.REGION)


def save_state(state):
    C.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    C.STATE_PATH.write_text(json.dumps(state, indent=2), encoding='utf-8')


def load_state():
    if C.STATE_PATH.exists():
        return json.loads(C.STATE_PATH.read_text(encoding='utf-8'))
    return {}


def wait_until(check, what, timeout=600, every=5):
    """Gọi check() lặp lại tới khi trả True hoặc hết giờ. In tiến độ cho dễ theo dõi."""
    start = time.time()
    while True:
        if check():
            return True
        waited = time.time() - start
        if waited > timeout:
            raise TimeoutError('Hết %ds khi chờ: %s' % (timeout, what))
        print('    ... đang chờ %s (%ds)' % (what, int(waited)))
        time.sleep(every)


# ===========================================================================
# PHẦN 1 — lấy thông tin có sẵn (VPC mặc định, AMI, IP của bạn)
# ===========================================================================
def default_network(ec2):
    """VPC mặc định + các subnet mặc định (ALB cần ít nhất 2 vùng sẵn sàng - AZ)."""
    vpcs = ec2.describe_vpcs(Filters=[{'Name': 'is-default', 'Values': ['true']}])['Vpcs']
    if not vpcs:
        raise SystemExit('❌ Region %s không có VPC mặc định. Tạo lại bằng: '
                         'aws ec2 create-default-vpc --region %s' % (C.REGION, C.REGION))
    vpc_id = vpcs[0]['VpcId']
    subnets = ec2.describe_subnets(Filters=[
        {'Name': 'vpc-id', 'Values': [vpc_id]},
        {'Name': 'default-for-az', 'Values': ['true']},
    ])['Subnets']
    azs = {s['AvailabilityZone'] for s in subnets}
    if len(azs) < 2:
        raise SystemExit('❌ ALB cần subnet ở ít nhất 2 AZ, hiện chỉ có: %s' % sorted(azs))
    return vpc_id, sorted(s['SubnetId'] for s in subnets)


def latest_ami(ssm):
    """AMI Amazon Linux 2023 mới nhất của region, qua tham số công khai."""
    return ssm.get_parameter(Name=C.AMI_PARAM)['Parameter']['Value']


def my_cidr():
    """Dải IP được gọi vào ALB. Mặc định = IP công khai hiện tại của máy bạn/32."""
    if C.ALLOWED_CIDR:
        return C.ALLOWED_CIDR
    with urllib.request.urlopen('https://checkip.amazonaws.com', timeout=10) as r:
        ip = r.read().decode().strip()
    return '%s/32' % ip


def user_data_script():
    """Script chạy MỘT LẦN khi máy khởi động (quyền root).

    Máy tự hỏi IMDS (dịch vụ metadata nội bộ của EC2) xem instance-id của mình,
    rồi phục vụ:  /        -> instance-id   (để lbtest biết request vào máy nào)
                  /health  -> ok            (để ALB health check)
    Dùng python3 có sẵn trong Amazon Linux 2023, không cần cài gì, không cần internet.
    Chạy server bằng systemd-run: thành một dịch vụ riêng, tự bật lại nếu chết.
    """
    return """#!/bin/bash
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
IID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
mkdir -p /srv/dt4n
echo "$IID" > /srv/dt4n/index.html
echo "ok" > /srv/dt4n/health
systemd-run --unit=dt4n-http -p Restart=always -p WorkingDirectory=/srv/dt4n /usr/bin/python3 -m http.server 80
"""


# ===========================================================================
# PHẦN 2 — tìm tài nguyên theo TÊN (để up không tạo trùng, down dọn được)
# ===========================================================================
def find_sg(ec2, name, vpc_id):
    groups = ec2.describe_security_groups(Filters=[
        {'Name': 'group-name', 'Values': [name]},
        {'Name': 'vpc-id', 'Values': [vpc_id]},
    ])['SecurityGroups']
    return groups[0]['GroupId'] if groups else None


def find_asg(asg):
    groups = asg.describe_auto_scaling_groups(
        AutoScalingGroupNames=[C.NAMES['asg']])['AutoScalingGroups']
    return groups[0] if groups else None


def find_alb(elb):
    try:
        lbs = elb.describe_load_balancers(Names=[C.NAMES['alb']])['LoadBalancers']
        return lbs[0] if lbs else None
    except ClientError as e:
        if e.response['Error']['Code'] == 'LoadBalancerNotFound':
            return None
        raise


def find_tg(elb):
    try:
        tgs = elb.describe_target_groups(Names=[C.NAMES['tg']])['TargetGroups']
        return tgs[0] if tgs else None
    except ClientError as e:
        if e.response['Error']['Code'] == 'TargetGroupNotFound':
            return None
        raise


def find_lt(ec2):
    try:
        lts = ec2.describe_launch_templates(
            LaunchTemplateNames=[C.NAMES['lt']])['LaunchTemplates']
        return lts[0] if lts else None
    except ClientError as e:
        if 'NotFound' in e.response['Error']['Code']:
            return None
        raise


# ===========================================================================
# PHẦN 3 — UP: dựng theo thứ tự phụ thuộc
#   SG -> launch template -> target group -> ALB + listener -> ASG
#   (ASG tham chiếu launch template và target group, nên tạo SAU CÙNG)
# ===========================================================================
def up():
    ec2, ssm, elb, asg = aws('ec2'), aws('ssm'), aws('elbv2'), aws('autoscaling')

    if find_asg(asg) or find_alb(elb):
        raise SystemExit('⚠️  Hạ tầng %s đã tồn tại. Chạy `status`, hoặc `down` '
                         'trước nếu muốn dựng lại.' % C.PREFIX)

    print('🔧 Region %s, tiền tố "%s", tối đa %d máy' % (C.REGION, C.PREFIX, C.MAX_SIZE))
    vpc_id, subnets = default_network(ec2)
    cidr = my_cidr()
    ami = latest_ami(ssm)
    print('  VPC %s, %d subnet, AMI %s' % (vpc_id, len(subnets), ami))
    print('  ALB chỉ nhận request từ %s' % cidr)
    state = {'region': C.REGION, 'vpc_id': vpc_id, 'subnets': subnets, 'ami': ami}

    # --- 1) Security group của ALB: IP của bạn -> cổng 80 ---
    alb_sg = ec2.create_security_group(
        GroupName=C.NAMES['alb_sg'], Description='DT4N ALB: HTTP from operator IP',
        VpcId=vpc_id,
        TagSpecifications=[{'ResourceType': 'security-group', 'Tags': C.tag_list()}],
    )['GroupId']
    ec2.authorize_security_group_ingress(GroupId=alb_sg, IpPermissions=[{
        'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80,
        'IpRanges': [{'CidrIp': cidr, 'Description': 'operator'}]}])
    state['alb_sg'] = alb_sg
    save_state(state)
    print('  ✅ security group ALB: %s' % alb_sg)

    # --- 2) Security group của máy: CHỈ ALB -> cổng 80 ---
    web_sg = ec2.create_security_group(
        GroupName=C.NAMES['web_sg'], Description='DT4N web: HTTP from ALB only',
        VpcId=vpc_id,
        TagSpecifications=[{'ResourceType': 'security-group', 'Tags': C.tag_list()}],
    )['GroupId']
    ec2.authorize_security_group_ingress(GroupId=web_sg, IpPermissions=[{
        'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80,
        'UserIdGroupPairs': [{'GroupId': alb_sg}]}])
    state['web_sg'] = web_sg
    save_state(state)
    print('  ✅ security group máy: %s' % web_sg)

    # --- 3) Launch template: khuôn đúc máy ---
    lt = ec2.create_launch_template(
        LaunchTemplateName=C.NAMES['lt'],
        LaunchTemplateData={
            'ImageId': ami,
            'InstanceType': C.INSTANCE_TYPE,
            'UserData': base64.b64encode(user_data_script().encode()).decode(),
            # IMDSv2 bắt buộc token: chặn một lớp tấn công SSRF phổ biến.
            'MetadataOptions': {'HttpTokens': 'required', 'HttpEndpoint': 'enabled'},
            # Không IP công khai: máy chỉ nói chuyện với ALB trong VPC.
            'NetworkInterfaces': [{
                'DeviceIndex': 0, 'AssociatePublicIpAddress': False,
                'Groups': [web_sg], 'DeleteOnTermination': True}],
            'TagSpecifications': [{'ResourceType': 'instance', 'Tags': C.tag_list() + [
                {'Key': 'Name', 'Value': '%s-web' % C.PREFIX}]}],
        },
        TagSpecifications=[{'ResourceType': 'launch-template', 'Tags': C.tag_list()}],
    )['LaunchTemplate']['LaunchTemplateId']
    state['launch_template'] = lt
    save_state(state)
    print('  ✅ launch template: %s (%s)' % (lt, C.INSTANCE_TYPE))

    # --- 4) Target group + health check nhanh (10 s, 2 lần liền) ---
    tg = elb.create_target_group(
        Name=C.NAMES['tg'], Protocol='HTTP', Port=80, VpcId=vpc_id,
        TargetType='instance', HealthCheckProtocol='HTTP', HealthCheckPath='/health',
        HealthCheckIntervalSeconds=10, HealthCheckTimeoutSeconds=5,
        HealthyThresholdCount=2, UnhealthyThresholdCount=2, Tags=C.tag_list(),
    )['TargetGroups'][0]['TargetGroupArn']
    # Gỡ máy khỏi ALB sau 10 s thay vì 300 s mặc định -> thu nhỏ nhanh hơn khi demo.
    elb.modify_target_group_attributes(TargetGroupArn=tg, Attributes=[
        {'Key': 'deregistration_delay.timeout_seconds', 'Value': '10'}])
    state['target_group'] = tg
    save_state(state)
    print('  ✅ target group: %s' % C.NAMES['tg'])

    # --- 5) ALB + listener cổng 80 ---
    alb = elb.create_load_balancer(
        Name=C.NAMES['alb'], Subnets=subnets, SecurityGroups=[alb_sg],
        Scheme='internet-facing', Type='application', IpAddressType='ipv4',
        Tags=C.tag_list(),
    )['LoadBalancers'][0]
    state['alb_arn'] = alb['LoadBalancerArn']
    state['alb_dns'] = alb['DNSName']
    save_state(state)
    elb.create_listener(LoadBalancerArn=alb['LoadBalancerArn'], Protocol='HTTP', Port=80,
                        DefaultActions=[{'Type': 'forward', 'TargetGroupArn': tg}])
    print('  ⏳ chờ ALB sẵn sàng (thường 2–4 phút)...')
    elb.get_waiter('load_balancer_available').wait(LoadBalancerArns=[alb['LoadBalancerArn']])
    print('  ✅ ALB: http://%s' % alb['DNSName'])

    # --- 6) ASG: bắt đầu 0 máy, tối đa MAX_SIZE ---
    asg.create_auto_scaling_group(
        AutoScalingGroupName=C.NAMES['asg'],
        LaunchTemplate={'LaunchTemplateName': C.NAMES['lt'], 'Version': '$Latest'},
        MinSize=0, MaxSize=C.MAX_SIZE, DesiredCapacity=0,
        VPCZoneIdentifier=','.join(subnets),
        TargetGroupARNs=[tg],
        # 'ELB' = ASG tin vào health check của ALB: máy không trả /health -> bị thay.
        HealthCheckType='ELB', HealthCheckGracePeriod=60,
        Tags=[{'Key': C.TAG_KEY, 'Value': C.TAG_VALUE, 'PropagateAtLaunch': True,
               'ResourceId': C.NAMES['asg'], 'ResourceType': 'auto-scaling-group'}],
    )
    state['asg'] = C.NAMES['asg']
    save_state(state)
    print('  ✅ ASG: %s (min 0, desired 0, max %d)' % (C.NAMES['asg'], C.MAX_SIZE))
    print('\n🎉 Xong. Thử: python3 -m cloud.infra scale 2   rồi   status')


# ===========================================================================
# PHẦN 4 — STATUS / SCALE / LBTEST
# ===========================================================================
def status():
    elb, asg = aws('elbv2'), aws('autoscaling')
    group, alb, tg = find_asg(asg), find_alb(elb), find_tg(elb)
    if not group:
        print('Chưa có ASG %s (chưa chạy `up`, hoặc đã `down`).' % C.NAMES['asg'])
        return
    insts = group['Instances']
    in_service = sum(1 for i in insts if i['LifecycleState'] == 'InService')
    print('ALB : http://%s' % (alb['DNSName'] if alb else '(không có)'))
    print('ASG : desired=%d  min=%d  max=%d  inService=%d  tổng máy=%d' % (
        group['DesiredCapacity'], group['MinSize'], group['MaxSize'], in_service, len(insts)))
    tg_health = {}
    if tg:
        for d in elb.describe_target_health(TargetGroupArn=tg['TargetGroupArn'])[
                'TargetHealthDescriptions']:
            tg_health[d['Target']['Id']] = d['TargetHealth']['State']
    for i in sorted(insts, key=lambda x: x['InstanceId']):
        print('  - %s  %-12s  lifecycle=%-12s asgHealth=%-9s albHealth=%s' % (
            i['InstanceId'], i['AvailabilityZone'], i['LifecycleState'],
            i['HealthStatus'], tg_health.get(i['InstanceId'], '-')))


def scale(n):
    """Đặt SỐ MÁY MONG MUỐN (lệnh đặt mức: gửi 2 lần vẫn ra đúng n máy)."""
    asg = aws('autoscaling')
    n = max(0, min(int(n), C.MAX_SIZE))
    asg.set_desired_capacity(AutoScalingGroupName=C.NAMES['asg'],
                             DesiredCapacity=n, HonorCooldown=False)
    print('✅ desired = %d (đã kẹp vào [0, %d])' % (n, C.MAX_SIZE))


def lbtest(n=30, url=None):
    """Gửi n request qua ALB, đếm mỗi máy (instance-id) nhận bao nhiêu."""
    if url is None:
        alb = find_alb(aws('elbv2'))
        if not alb:
            raise SystemExit('Không thấy ALB. Chạy `up` trước.')
        url = 'http://%s/' % alb['DNSName']
    counts, errors = collections.Counter(), 0
    for _ in range(int(n)):
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                counts[r.read().decode().strip()] += 1
        except Exception as e:  # noqa: BLE001 — đếm lỗi, không dừng
            errors += 1
            last_err = e
    print('Gửi %d request tới %s' % (n, url))
    for iid, c in counts.most_common():
        print('  %-22s %3d  (%4.1f%%)' % (iid, c, 100.0 * c / n))
    if errors:
        print('  lỗi: %d (lỗi cuối: %s)' % (errors, last_err))
    return counts, errors


# ===========================================================================
# PHẦN 5 — DOWN: dọn theo thứ tự NGƯỢC, tìm theo tên, chờ đến khi xong thật
# ===========================================================================
def down():
    ec2, elb, asg = aws('ec2'), aws('elbv2'), aws('autoscaling')
    print('🧹 Dọn hạ tầng "%s" ở %s' % (C.PREFIX, C.REGION))

    # 1) ASG: ForceDelete = xóa luôn các máy bên trong.
    if find_asg(asg):
        asg.delete_auto_scaling_group(AutoScalingGroupName=C.NAMES['asg'], ForceDelete=True)
        wait_until(lambda: find_asg(asg) is None, 'ASG và các máy bị xóa', every=10)
    print('  ✅ ASG')

    # 2) ALB (listener bị xóa theo).
    alb = find_alb(elb)
    if alb:
        elb.delete_load_balancer(LoadBalancerArn=alb['LoadBalancerArn'])
        elb.get_waiter('load_balancers_deleted').wait(LoadBalancerArns=[alb['LoadBalancerArn']])
    print('  ✅ ALB')

    # 3) Target group (đôi khi còn "đang dùng" vài giây sau khi ALB đi).
    tg = find_tg(elb)
    if tg:
        def _del_tg():
            try:
                elb.delete_target_group(TargetGroupArn=tg['TargetGroupArn'])
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceInUse':
                    return False
                raise
        wait_until(_del_tg, 'target group được giải phóng')
    print('  ✅ target group')

    # 4) Launch template.
    if find_lt(ec2):
        ec2.delete_launch_template(LaunchTemplateName=C.NAMES['lt'])
    print('  ✅ launch template')

    # 5) Security group: phải chờ card mạng của máy/ALB được trả hết.
    vpcs = ec2.describe_vpcs(Filters=[{'Name': 'is-default', 'Values': ['true']}])['Vpcs']
    vpc_id = vpcs[0]['VpcId'] if vpcs else None
    for key in ('web_sg', 'alb_sg'):          # web-sg tham chiếu alb-sg -> xóa web trước
        sg = find_sg(ec2, C.NAMES[key], vpc_id) if vpc_id else None
        if not sg:
            continue

        def _del_sg(sg=sg):
            try:
                ec2.delete_security_group(GroupId=sg)
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == 'DependencyViolation':
                    return False
                raise
        wait_until(_del_sg, 'security group %s hết bị dùng' % C.NAMES[key], every=10)
    print('  ✅ security group')

    # 6) Kiểm tra sót: còn máy nào mang tag Project=dt4n đang chạy không?
    left = ec2.describe_instances(Filters=[
        {'Name': 'tag:%s' % C.TAG_KEY, 'Values': [C.TAG_VALUE]},
        {'Name': 'instance-state-name', 'Values': ['pending', 'running', 'stopping', 'stopped']},
    ])['Reservations']
    ids = [i['InstanceId'] for r in left for i in r['Instances']]
    if ids:
        print('  ⚠️  còn máy sót, đang terminate: %s' % ids)
        ec2.terminate_instances(InstanceIds=ids)
    else:
        print('  ✅ không còn máy nào mang tag %s=%s' % (C.TAG_KEY, C.TAG_VALUE))

    if C.STATE_PATH.exists():
        C.STATE_PATH.unlink()
    print('\n🎉 Đã dọn xong.')


# ===========================================================================
def main(argv=None):
    p = argparse.ArgumentParser(description='Hạ tầng AWS cho DT4N (GĐ1)')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('up')
    sub.add_parser('status')
    s = sub.add_parser('scale')
    s.add_argument('n', type=int)
    t = sub.add_parser('lbtest')
    t.add_argument('n', type=int, nargs='?', default=30)
    sub.add_parser('down')
    a = p.parse_args(argv)
    if a.cmd == 'up':
        up()
    elif a.cmd == 'status':
        status()
    elif a.cmd == 'scale':
        scale(a.n)
    elif a.cmd == 'lbtest':
        lbtest(a.n)
    elif a.cmd == 'down':
        down()


if __name__ == '__main__':
    sys.exit(main())
