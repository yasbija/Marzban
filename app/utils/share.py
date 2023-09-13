import base64
import json
import random
import secrets
import urllib.parse as urlparse
from datetime import datetime as dt
from typing import TYPE_CHECKING, Literal, Union, List
from uuid import UUID

import yaml

from app import xray
from app.models.proxy import FormatVariables
from app.templates import render_template
from app.utils.system import get_public_ip, readable_size

if TYPE_CHECKING:
    from app.models.user import UserResponse

from config import CLASH_SUBSCRIPTION_TEMPLATE, SINGBOX_SUBSCRIPTION_TEMPLATE

SERVER_IP = get_public_ip()

STATUS_EMOJIES = {
    'active': '✅',
    'expired': '⌛️',
    'limited': '🪫',
    'disabled': '❌'
}


class V2rayShareLink(str):
    @classmethod
    def vmess(cls,
              remark: str,
              address: str,
              port: int,
              id: Union[str, UUID],
              host='',
              net='tcp',
              path='',
              type='',
              tls='none',
              sni='',
              fp='',
              alpn='',
              pbk='',
              sid='',
              spx=''):

        payload = {
            'add': address,
            'aid': '0',
            'host': host,
            'id': str(id),
            'net': net,
            'path': path,
            'port': port,
            'ps': remark,
            'scy': 'auto',
            'tls': tls,
            'type': type,
            'v': '2'
        }

        if tls == 'tls':
            payload['sni'] = sni
            payload['fp'] = fp
            payload['alpn'] = alpn
        elif tls == 'reality':
            payload['sni'] = sni
            payload['fp'] = fp
            payload['pbk'] = pbk
            payload['sid'] = sid
            payload['spx'] = spx

        return "vmess://" + base64.b64encode(json.dumps(payload, sort_keys=True).encode('utf-8')).decode()

    @classmethod
    def vless(cls,
              remark: str,
              address: str,
              port: int,
              id: Union[str, UUID],
              net='ws',
              path='',
              host='',
              type='',
              flow='',
              tls='none',
              sni='',
              fp='',
              alpn='',
              pbk='',
              sid='',
              spx=''):

        payload = {
            "security": tls,
            "type": net,
            "host": host,
            "headerType": type
        }
        if flow and net in ('tcp', 'kcp'):
            payload['flow'] = flow

        if net == 'grpc':
            payload['serviceName'] = path
        else:
            payload['path'] = path

        if tls == 'tls':
            payload['sni'] = sni
            payload['fp'] = fp
            payload['alpn'] = alpn
        elif tls == 'reality':
            payload['sni'] = sni
            payload['fp'] = fp
            payload['pbk'] = pbk
            payload['sid'] = sid
            payload['spx'] = spx

        return "vless://" + \
            f"{id}@{address}:{port}?" + \
            urlparse.urlencode(payload) + f"#{( urlparse.quote(remark))}"

    @classmethod
    def trojan(cls,
               remark: str,
               address: str,
               port: int,
               password: str,
               net='tcp',
               path='',
               host='',
               type='',
               flow='',
               tls='none',
               sni='',
               fp='',
               alpn='',
               pbk='',
               sid='',
               spx=''):

        payload = {
            "security": tls,
            "type": net,
            "host": host,
            "headerType": type
        }
        if flow and net in ('tcp', 'kcp'):
            payload['flow'] = flow

        if net == 'grpc':
            payload['serviceName'] = path
        else:
            payload['path'] = path

        if tls == 'tls':
            payload['sni'] = sni
            payload['fp'] = fp
            payload['alpn'] = alpn
        elif tls == 'reality':
            payload['sni'] = sni
            payload['fp'] = fp
            payload['pbk'] = pbk
            payload['sid'] = sid
            payload['spx'] = spx

        return "trojan://" + \
            f"{urlparse.quote(password, safe=':')}@{address}:{port}?" + \
            urlparse.urlencode(payload) + f"#{urlparse.quote(remark)}"

    @classmethod
    def shadowsocks(cls,
                    remark: str,
                    address: str,
                    port: int,
                    password: str,
                    security='chacha20-ietf-poly1305'):
        return "ss://" + \
            base64.b64encode(f'{security}:{password}'.encode()).decode() + \
            f"@{address}:{port}#{urlparse.quote(remark)}"


class ClashConfiguration(object):
    def __init__(self):
        self.data = {
            'proxies': [],
            'proxy-groups': [],
            # Some clients rely on "rules" option and will fail without it.
            'rules': []
        }
        self.proxy_remarks = []

    def render(self):
        return yaml.dump(
            yaml.load(
                render_template(
                    CLASH_SUBSCRIPTION_TEMPLATE,
                    {"conf": self.data, "proxy_remarks": self.proxy_remarks}
                ),
                Loader=yaml.SafeLoader
            ),
            sort_keys=False,
            allow_unicode=True
        )

    def __str__(self) -> str:
        return self.to_yaml()

    def __repr__(self) -> str:
        return self.to_yaml()

    def _remark_validation(self, remark):
        if not remark in self.proxy_remarks:
            return remark
        c = 2
        while True:
            new = f'{remark} ({c})'
            if not new in self.proxy_remarks:
                return new
            c += 1

    def make_node(self,
                  name: str,
                  type: str,
                  server: str,
                  port: int,
                  network: str,
                  tls: bool,
                  sni: str,
                  host: str,
                  path: str,
                  udp: bool = True,
                  alpn: str = ''):
        remark = self._remark_validation(name)
        node = {
            'name': remark,
            'type': type,
            'server': server,
            'port': port,
            'network': network,
            f'{network}-opts': {},
            'udp': udp
        }

        if type == 'ss':  # shadowsocks
            return node

        if tls:
            node['tls'] = True
            if type == 'trojan':
                node['sni'] = sni
            else:
                node['servername'] = sni
            if alpn:
                node['alpn'] = alpn.split(',')

        net_opts = node[f'{network}-opts']

        if network == 'ws':
            if path:
                net_opts['path'] = path
            if host:
                net_opts['headers'] = {"Host": host}

        if network == 'grpc':
            if path:
                net_opts['grpc-service-name'] = path

        if network == 'h2':
            if path:
                net_opts['path'] = path
            if host:
                net_opts['host'] = [host]

        if network == 'http' or network == 'tcp':
            if path:
                net_opts['method'] = 'GET'
                net_opts['path'] = [path]
            if host:
                net_opts['method'] = 'GET'
                net_opts['headers'] = {"Host": host}

        return node

    def add(self, remark: str, address: str, inbound: dict, settings: dict):
        node = self.make_node(
            name=remark,
            type=inbound['protocol'],
            server=address,
            port=inbound['port'],
            network=inbound['network'],
            tls=(inbound['tls'] == 'tls'),
            sni=inbound['sni'],
            host=inbound['host'],
            path=inbound['path'],
            udp=True,
            alpn=inbound.get('alpn', ''),
        )

        if inbound['protocol'] == 'vmess':
            node['uuid'] = settings['id']
            node['alterId'] = 0
            node['cipher'] = 'auto'
            self.data['proxies'].append(node)
            self.proxy_remarks.append(remark)

        if inbound['protocol'] == 'trojan':
            node['password'] = settings['password']
            self.data['proxies'].append(node)
            self.proxy_remarks.append(remark)

        if inbound['protocol'] == 'shadowsocks':
            node['password'] = settings['password']
            self.data['proxies'].append(node)
            self.proxy_remarks.append(remark)


class ClashMetaConfiguration(ClashConfiguration):
    def make_node(self,
                  name: str,
                  type: str,
                  server: str,
                  port: int,
                  network: str,
                  tls: bool,
                  sni: str,
                  host: str,
                  path: str,
                  udp: bool = True,
                  alpn: str = '',
                  fp: str = '',
                  pbk: str = '',
                  sid: str = ''):
        node = super().make_node(
            name=name,
            type=type,
            server=server,
            port=port,
            network=network,
            tls=tls,
            sni=sni,
            host=host,
            path=path,
            udp=udp,
            alpn=alpn
        )
        if fp:
            node['client-fingerprint'] = fp
        if pbk:
            node['reality-opts'] = {"public-key": pbk, "short-id": sid}

        return node

    def add(self, remark: str, address: str, inbound: dict, settings: dict):
        node = self.make_node(
            name=remark,
            type=inbound['protocol'],
            server=address,
            port=inbound['port'],
            network=inbound['network'],
            tls=(inbound['tls'] in ('tls', 'reality')),
            sni=inbound['sni'],
            host=inbound['host'],
            path=inbound['path'],
            udp=True,
            alpn=inbound.get('alpn', ''),
            fp=inbound.get('fp', ''),
            pbk=inbound.get('pbk', ''),
            sid=inbound.get('sid', ''),
        )

        if inbound['protocol'] == 'vmess':
            node['uuid'] = settings['id']
            node['alterId'] = 0
            node['cipher'] = 'auto'
            self.data['proxies'].append(node)
            self.proxy_remarks.append(remark)

        if inbound['protocol'] == 'vless':
            node['uuid'] = settings['id']

            if inbound['network'] in ('tcp', 'kcp'):
                node['flow'] = settings.get('flow', '')

            self.data['proxies'].append(node)
            self.proxy_remarks.append(remark)

        if inbound['protocol'] == 'trojan':
            node['password'] = settings['password']

            if inbound['network'] in ('tcp', 'kcp'):
                node['flow'] = settings.get('flow', '')

            self.data['proxies'].append(node)
            self.proxy_remarks.append(remark)

        if inbound['protocol'] == 'shadowsocks':
            node['password'] = settings['password']
            self.data['proxies'].append(node)
            self.proxy_remarks.append(remark)


def get_v2ray_link(remark: str, address: str, inbound: dict, settings: dict):
    if inbound['protocol'] == 'vmess':
        return V2rayShareLink.vmess(remark=remark,
                                    address=address,
                                    port=inbound['port'],
                                    id=settings['id'],
                                    net=inbound['network'],
                                    tls=inbound['tls'],
                                    sni=inbound.get('sni', ''),
                                    fp=inbound.get('fp', ''),
                                    alpn=inbound.get('alpn', ''),
                                    pbk=inbound.get('pbk', ''),
                                    sid=inbound.get('sid', ''),
                                    spx=inbound.get('spx', ''),
                                    host=inbound['host'],
                                    path=inbound['path'],
                                    type=inbound['header_type'])

    if inbound['protocol'] == 'vless':
        return V2rayShareLink.vless(remark=remark,
                                    address=address,
                                    port=inbound['port'],
                                    id=settings['id'],
                                    flow=settings.get('flow', ''),
                                    net=inbound['network'],
                                    tls=inbound['tls'],
                                    sni=inbound.get('sni', ''),
                                    fp=inbound.get('fp', ''),
                                    alpn=inbound.get('alpn', ''),
                                    pbk=inbound.get('pbk', ''),
                                    sid=inbound.get('sid', ''),
                                    spx=inbound.get('spx', ''),
                                    host=inbound['host'],
                                    path=inbound['path'],
                                    type=inbound['header_type'])

    if inbound['protocol'] == 'trojan':
        return V2rayShareLink.trojan(remark=remark,
                                     address=address,
                                     port=inbound['port'],
                                     password=settings['password'],
                                     flow=settings.get('flow', ''),
                                     net=inbound['network'],
                                     tls=inbound['tls'],
                                     sni=inbound.get('sni', ''),
                                     fp=inbound.get('fp', ''),
                                     alpn=inbound.get('alpn', ''),
                                     pbk=inbound.get('pbk', ''),
                                     sid=inbound.get('sid', ''),
                                     spx=inbound.get('spx', ''),
                                     host=inbound['host'],
                                     path=inbound['path'],
                                     type=inbound['header_type'])

    if inbound['protocol'] == 'shadowsocks':
        return V2rayShareLink.shadowsocks(remark=remark,
                                          address=address,
                                          port=inbound['port'],
                                          password=settings['password'])


class SingBoxConfiguration(str):

    def __init__(self):
        template = render_template(SINGBOX_SUBSCRIPTION_TEMPLATE)
        self.config = json.loads(template)
    
    def add_outbound(self, outbound_data):
        self.config["outbounds"].append(outbound_data)
    
    def render(self):
        urltest_types = ["vmess", "vless", "trojan", "shadowsocks"]
        urltest_tags = [outbound["tag"] for outbound in self.config["outbounds"] if outbound["type"] in urltest_types]
        selector_types = ["vmess", "vless", "trojan", "shadowsocks", "urltest"]
        selector_tags = [outbound["tag"] for outbound in self.config["outbounds"] if outbound["type"] in selector_types]

        for outbound in self.config["outbounds"]:
            if outbound.get("type") == "urltest":
                outbound["outbounds"] = urltest_tags

        for outbound in self.config["outbounds"]:
            if outbound.get("type") == "selector" :
                outbound["outbounds"] = selector_tags

        return json.dumps(self.config, indent=4)
    
    @staticmethod
    def tls_config(sni=None, fp=None, tls=None, pbk=None, 
                   sid=None, alpn=None, ais=None):
        
        config = {}
        if tls in  ['tls','reality']:
            config["enabled"] = True
        
        if sni is not None:
            config["server_name"] = sni

        if tls is 'tls' and ais:
            config['insecure'] = ais

        if tls == 'reality':
            config["reality"] = {"enabled": True}
            if pbk:
                config["reality"]["public_key"] = pbk
            if sid:
                config["reality"]["short_id"] = sid

        if fp:
            config["utls"] = {
                "enabled": bool(fp),
                "fingerprint": fp
            }

        if alpn:
            config["alpn"] = [alpn] if not isinstance(alpn, list) else alpn

        return config

    @staticmethod
    def transport_config(transport_type='',
                         host='',
                         path='',
                         method='',
                         headers='',
                         idle_timeout="15s",
                         ping_timeout="15s",
                         max_early_data=None,
                         early_data_header_name=None,
                         permit_without_stream=False):
        
        transport_config = {}
        
        if transport_type:
            transport_config['type'] = transport_type
            
            if transport_type == "http":
                if host:
                    transport_config['host'] = host
                if path:
                    transport_config['path'] = path
                if method:
                    transport_config['method'] = method
                if headers:
                    transport_config['headers'] = headers
                if idle_timeout:
                    transport_config['idle_timeout'] = idle_timeout
                if ping_timeout:
                    transport_config['ping_timeout'] = ping_timeout
            
            elif transport_type == "ws":
                if path:
                    transport_config['path'] = path
                if headers:
                    transport_config['headers'] = headers
                if max_early_data is not None:
                    transport_config['max_early_data'] = max_early_data
                if early_data_header_name:
                    transport_config['early_data_header_name'] = early_data_header_name
            
            elif transport_type == "grpc":
                if path:
                    transport_config['service_name'] = path
                if idle_timeout:
                    transport_config['idle_timeout'] = idle_timeout
                if ping_timeout:
                    transport_config['ping_timeout'] = ping_timeout
                if permit_without_stream:
                    transport_config['permit_without_stream'] = permit_without_stream

        return transport_config
    
    def make_outbound(self,
                  type: str,
                  remark: str,
                  address: str,
                  port: int,
                  net='ws',
                  path='',
                  host='',
                  flow='',
                  tls='',
                  sni='',
                  fp='',
                  alpn='',
                  pbk='',
                  sid='',
                  headers='',
                  ais=''):

        config = {
            "type": type,
            "tag": remark,
            "server": address,
            "server_port": port,
        }
        if net in ('tcp', 'kcp'):
            if flow:
                config["flow"] = flow

        if net in ['http', 'ws', 'quic', 'grpc', 'h2']:
            if net == 'h2':
                net = 'http'
                alpn = 'h2'
            config['transport'] = self.transport_config(
                transport_type=net,
                host=host,
                path=path,
                headers=headers
            )
        else:
            config["network"]: net

        if tls in ('tls', 'reality'):
            config['tls'] = self.tls_config(sni=sni, fp=fp, tls=tls, 
                                            pbk=pbk, sid=sid, alpn=alpn,
                                            ais=ais)

        return config

    def add(self, remark: str, address: str, inbound: dict, settings: dict):
        outbound = self.make_outbound(
            remark=remark,
            type=inbound['protocol'],
            address=address,
            port=inbound['port'],
            net=inbound['network'],
            tls=(inbound['tls']),
            flow=settings.get('flow', ''),
            sni=inbound['sni'],
            host=inbound['host'],
            path=inbound['path'],
            alpn=inbound.get('alpn', ''),
            fp=inbound.get('fp', ''),
            pbk=inbound.get('pbk', ''),
            sid=inbound.get('sid', ''),
            headers=inbound['header_type'],
            ais=inbound.get('ais', ''))

        if inbound['protocol'] == 'vmess':
            outbound['uuid'] = settings['id']

        elif inbound['protocol'] == 'vless':
            outbound['uuid'] = settings['id']

        elif inbound['protocol'] == 'trojan':
            outbound['password'] = settings['password']

        elif inbound['protocol'] == 'shadowsocks':
            outbound['password'] = settings['password']
            outbound['method'] = settings['method']

        self.add_outbound(outbound)


def generate_v2ray_links(proxies: dict, inbounds: dict, extra_data: dict) -> list:
    format_variables = setup_format_variables(extra_data)
    return process_inbounds_and_tags(inbounds, proxies, format_variables, mode="v2ray")


def generate_clash_subscription(proxies: dict, inbounds: dict, extra_data: dict, is_meta: bool = False) -> str:
    if is_meta is True:
        conf = ClashMetaConfiguration()
    else:
        conf = ClashConfiguration()

    format_variables = setup_format_variables(extra_data)
    return process_inbounds_and_tags(inbounds, proxies, format_variables, mode="clash", conf=conf)


def generate_singbox_subscription(proxies: dict, inbounds: dict, extra_data: dict) -> str:
    conf = SingBoxConfiguration()

    format_variables = setup_format_variables(extra_data)
    return process_inbounds_and_tags(inbounds, proxies, format_variables, mode="sing-box", conf=conf)


def generate_v2ray_subscription(links: list) -> str:
    return base64.b64encode('\n'.join(links).encode()).decode()


def generate_subscription(
    user: "UserResponse",
    config_format: Literal["v2ray", "clash-meta", "clash", "sing-box"],
    as_base64: bool
) -> str:
    kwargs = {"proxies": user.proxies, "inbounds": user.inbounds, "extra_data": user.__dict__}

    if config_format == 'v2ray':
        config = "\n".join(generate_v2ray_links(**kwargs))
    elif config_format == 'clash-meta':
        config = generate_clash_subscription(**kwargs, is_meta=True)
    elif config_format == 'clash':
        config = generate_clash_subscription(**kwargs)
    elif config_format == 'sing-box':
        config = generate_singbox_subscription(**kwargs)
    else:
        raise ValueError(f'Unsupported format "{config_format}"')

    if as_base64:
        config = base64.b64encode(config.encode()).decode()

    return config


def format_time_left(expire: int) -> str:
    seconds_left = expire - int(dt.now().timestamp())

    if seconds_left <= 0:
        return

    minutes, seconds = divmod(seconds_left, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    months, days = divmod(days, 30)

    result = []
    if months:
        result.append(f"{months}m")
    if days:
        result.append(f"{days}d")
    if hours and (days < 7):
        result.append(f"{hours}h")
    if minutes and not (months or days):
        result.append(f"{minutes}m")
    if seconds and not (months or days):
        result.append(f"{seconds}s")
    return ' '.join(result)


def setup_format_variables(extra_data: dict) -> dict:

    if (extra_data.get('expire') or 0) > 0:
        days_left = (dt.fromtimestamp(extra_data['expire']) - dt.now()).days + 1
        if not days_left > 0:
            days_left = 0
            time_left = 0
        elif days_left:
            time_left = format_time_left(extra_data['expire'])
    else:
        days_left = '∞'
        time_left = '∞'

    if extra_data.get('data_limit'):
        data_limit = readable_size(extra_data['data_limit'])
        data_left = extra_data['data_limit'] - extra_data['used_traffic']
        if data_left < 0:
            data_left = 0
        data_left = readable_size(data_left)
    else:
        data_limit = '∞'
        data_left = '∞'

    status_emoji = STATUS_EMOJIES.get(extra_data.get('status')) or ''

    format_variables = {
        "SERVER_IP": SERVER_IP,
        "USERNAME": extra_data.get('username', '{USERNAME}'),
        "DATA_USAGE": readable_size(extra_data.get('used_traffic')),
        "DATA_LIMIT": data_limit,
        "DATA_LEFT": data_left,
        "DAYS_LEFT": days_left,
        "TIME_LEFT": time_left,
        "STATUS_EMOJI": status_emoji
    }

    return format_variables


def process_inbounds_and_tags(inbounds: dict, proxies: dict, format_variables: dict, 
                              mode: str="v2ray", conf= None) -> Union[List, str]:
    salt = secrets.token_hex(8)
    results = []

    for protocol, tags in inbounds.items():
        settings = proxies.get(protocol)
        if not settings:
            continue

        format_variables.update({"PROTOCOL": protocol.name})
        for tag in tags:
            inbound = xray.config.inbounds_by_tag.get(tag)
            if not inbound:
                continue

            format_variables.update({"TRANSPORT": inbound['network']})
            host_inbound = inbound.copy()
            for host in xray.hosts.get(tag, []):
                sni = ''
                sni_list = host['sni'] or inbound['sni']
                if sni_list:
                    sni = random.choice(sni_list).replace('*', salt)

                req_host = ''
                req_host_list = host['host'] or inbound['host']
                if req_host_list:
                    req_host = random.choice(req_host_list).replace('*', salt)

                host_inbound.update({
                    'port': host['port'] or inbound['port'],
                    'sni': sni,
                    'host': req_host,
                    'tls': inbound['tls'] if host['tls'] is None else host['tls'],
                    'alpn': host['alpn'] or inbound.get('alpn', ''),
                    'fp': host['fingerprint'] or inbound.get('fp', '')
                })

                if mode == "v2ray":
                    results.append(get_v2ray_link(remark=host['remark'].format_map(format_variables),
                                                  address=host['address'].format_map(format_variables),
                                                  inbound=host_inbound,
                                                  settings=settings.dict(no_obj=True)))
                elif mode in ["clash", "sing-box"]:
                    conf.add(
                        remark=host['remark'].format_map(format_variables),
                        address=host['address'].format_map(format_variables),
                        inbound=host_inbound,
                        settings=settings.dict(no_obj=True),
                    )
                    
    if mode in ["clash", "sing-box"]:
        return conf.render()
    
    return results
