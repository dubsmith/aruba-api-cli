# MIT License
#
# Copyright (c) 2020 Aruba, a Hewlett Packard Enterprise company
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import getpass
import requests
import yaml
import pprint
import os
import json
from typing import Union
import urllib.parse
import csv
from . import Response

try:
    from . import utils
except ImportError:
    from utils import Utils  # type: ignore
    utils = Utils()


_refresh_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config", ".refresh_token.yaml"))
_config_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config", "config.yaml"))
_bulk_edit_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config", 'bulkedit.csv'))


class CentralApiAuth:

    def __init__(self, vars: Union[dict, None] = None):
        if utils.valid_file(_refresh_file):
            self.refresh_token = utils.read_yaml(_refresh_file)

        if utils.valid_file(_config_file):
            self.vars = utils.read_yaml(_config_file)

        if not self.refresh_token:
            print("No refresh token located, attempting full authentication workflow")
            self.login_data = self.login()
            self.auth_code = self.authorize()

        self.access_token = self.tokens()
        self.headers = {"authorization": f"Bearer {self.access_token}"}

    def login(self):
        """Build and post login call

       :param vars: imported variables
       :type vars: Python dict
       :return: CSRF and Session data
       :rtype: Python dict
       """
        login_url = self.vars["base_url"] + "/oauth2/authorize/central/api/login"
        params = {"client_id": self.vars["client_id"]}
        payload = {"username": self.vars["username"], "password": getpass.getpass()}
        resp = requests.post(login_url, params=params, json=payload, timeout=10)
        if resp.json()["status"]:
            print("Login Successful")
        else:
            print("Login Failed")
            exit()
        login_data = {"csrf": resp.cookies["csrftoken"], "ses": resp.cookies["session"]}
        return login_data

    def authorize(self):
        """Build and post authorization grant call

        :param vars: imported variables
        :type vars: Python dict
        :param login_data: Data from login function
        :type login_data: Python dict
        :return: Authorization code
        :rtype: String
        """
        auth_url = self.vars["base_url"] + "/oauth2/authorize/central/api"
        ses = "session=" + self.login_data["ses"]
        headers = {
            "X-CSRF-TOKEN": self.login_data["csrf"],
            "Content-type": "application/json",
            "Cookie": ses,
        }
        payload = {"customer_id": self.vars["customer_id"]}
        params = {
            "client_id": self.vars["client_id"],
            "response_type": "code",
            "scope": "all",
        }
        resp = requests.post(auth_url, params=params, json=payload, headers=headers)
        return resp.json()["auth_code"]

    def tokens(self):
        """Import refresh token, post call, write new refresh and return access token.

        :param vars: Imported variables for client
        :type vars: Python dict
        :return: Access token
        :rtype: String
        """
        token_url = self.vars["base_url"] + "/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": str(self.refresh_token["refresh_token"]),
        }
        resp = requests.post(
            token_url,
            data=data,
            auth=(self.vars["client_id"], self.vars["client_secret"]),
        )
        refresh_token = resp.json()["refresh_token"]
        access_token = resp.json()["access_token"]
        self.write_to_file(refresh_token)
        return access_token

    def full_tokens(self):
        """Build & post call for access & refresh tokens. Write refresh token

        :param vars: Imported variables
        :type vars: Python dict
        :param auth_code: Authorization code from authorization func
        :type auth_code: String
        :return: Access token
        :rtype: String
        """
        auth_url = self.vars["base_url"] + "/oauth2/token"
        data = {"grant_type": "authorization_code", "code": self.auth_code}
        resp = requests.post(
            auth_url,
            data=data,
            auth=(self.vars["client_id"], self.vars["client_secret"]),
        )
        refresh_token = resp.json()["refresh_token"]
        access_token = resp.json()["access_token"]
        self.write_to_file(refresh_token)
        return access_token

    def write_to_file(self, token):
        """Write refresh token to local yaml file

        :param token: Refresh token
        :type token: String
        """
        data = {"refresh_token": token}
        # TODO log print(f"Writing refresh token to {_refresh_file}")
        with open(_refresh_file, "w") as write_file:
            yaml.dump(data, write_file)

    def get(self, url, params: dict = None, headers: dict = None):
        """Generic GET call

        :param vars: Imported variables
        :type vars: Python dict
        :param url: GET call URL
        :type url: String
        :param header: GET call parameters
        :type header: Python dict
        :return: GET call response JSON
        :rtype: Python dict
        """
        if headers is None:
            headers = self.headers
        f_url = self.vars["base_url"] + url
        return Response(requests.get, f_url, params=params, headers=headers)


class CentralApi:
    def __init__(self, central: CentralApiAuth = CentralApiAuth()):
        # if not central:
        #     self.central =
        # else:
        self.central = central

    def get_ap(self):
        """GET call for AP data

        :param access_token: Access token from tokens func
        :type access_token: String
        """
        url = "/monitoring/v1/aps"
        return self.central.get(url)

    def get_swarms_by_group(self, group: str):
        url = "/monitoring/v1/swarms"
        params = {"group": group}
        return self.central.get(url, params=params)

    def get_swarm_details(self, swarm_id: str):
        url = f"/monitoring/v1/swarms/{swarm_id}"
        return self.central.get(url)

    def get_wlan_clients(self, group: str = None, swarm_id: str = None, label: str = None, ssid: str = None,
                         serial: str = None, os_type: str = None, cluster_id: str = None, band: str = None) -> None:
        params = {}
        for k, v in zip(["group", "swarm_id", "label", "ssid", "serial", "os_type", "cluster_id", "band"],
                        [group, swarm_id, label, ssid, serial, os_type, cluster_id, band]
                        ):
            if v:
                params[k] = v

        url = "/monitoring/v1/clients/wireless"
        return self.central.get(url, params=params)

    def get_wired_clients(self, group: str = None, swarm_id: str = None, label: str = None, ssid: str = None,
                          serial: str = None, cluster_id: str = None, stack_id: str = None) -> None:
        params = {}
        for k, v in zip(["group", "swarm_id", "label", "ssid", "serial", "cluster_id", "stack_id"],
                        [group, swarm_id, label, ssid, serial, cluster_id, stack_id]
                        ):
            if v:
                params[k] = v

        url = "/monitoring/v1/clients/wired"
        return self.central.get(url, params=params)

    def get_client_details(self, mac: str):
        url = f"/monitoring/v1/clients/wired/{urllib.parse.quote(mac)}"
        return self.central.get(url)

    def get_certificates(self):
        url = "/configuration/v1/certificates"
        params = {"limit": 20, "offset": 0}
        return self.central.get(url, params=params)

    def get_template(self, group, template):
        url = f"/configuration/v1/groups/{group}/templates/{template}"
        # header = {"authorization": f"Bearer {self.access_token}"}
        # resp = requests.get(self.auth.vars["base_url"] + url)
        # print(resp.text)
        return self.central.get(url)

    def get_all_groups(self):  # DONE
        url = "/configuration/v2/groups?limit=20&offset=0"
        params = {"limit": 20, "offset": 0}
        # header = {"authorization": f"Bearer {self.access_token}"}
        return self.central.get(url, params=params)
        # return resp

    def get_sku_types(self):
        url = "/platform/orders/v1/skus"
        params = {"sku_type": "all"}
        return self.central.get(url, params=params)

    def get_dev_by_type(self, dev_type):
        url = "/platform/device_inventory/v1/devices"
        if dev_type.lower() in ["aps", "ap"]:
            dev_type = "iap"
        params = {"sku_type": dev_type}
        # header = {"authorization": f"Bearer {self.auth.access_token}"}
        return self.central.get(url, params=params)
        # resp = self.get_call(url, params)
        # return resp if "devices" not in resp else resp["devices"]

    def get_variablised_template(self, serialnum):
        url = f"/configuration/v1/devices/{serialnum}/variablised_template"
        # header = {"authorization": f"Bearer {self.access_token}"}
        return self.central.get(url)
        # return(resp.text.split('\n'))

    def get_variables(self, serialnum: str = None):
        if serialnum:
            url = f"/configuration/v1/devices/{serialnum}/template_variables"
            params = {}
        else:
            url = "/configuration/v1/devices/template_variables"
            params = {"limit": 20, "offset": 0}
            # TODO generator for returns > 20 devices
        return self.central.get(url, params=params)
        # resp = requests.get(self.vars["base_url"] + url, params=params, headers=header)
        # return(resp.json())

    # TODO self.central.patch
    def update_variables(self, serialnum: str, var_dict: dict):
        url = f"/configuration/v1/devices/{serialnum}/template_variables"
        header = {
                    "authorization": f"Bearer {self.central.access_token}",
                    "Content-type": "application/json"
                 }
        var_dict = json.dumps(var_dict)
        resp = requests.patch(self.central.vars["base_url"] + url, data=var_dict, headers=header)
        return(resp.ok)

    def get_ssids_by_group(self, group):
        url = "/monitoring/v1/networks"
        params = {"group": group}
        return self.central.get(url, params=params)

    def get_gateways_by_group(self, group):
        url = "/monitoring/v1/mobility_controllers"
        params = {"group": group}
        return self.get.central.get(url, params=params)
        # return resp if 'mcs' not in resp else resp['mcs']

    def get_group_for_dev_by_serial(self, serial_num):
        return self.central.get(f"/configuration/v1/devices/{serial_num}/group")
        # return resp if "group" not in resp else resp["group"]

    def get_dhcp_client_info_by_gw(self, serial_num):
        url = f"/monitoring/v1/mobility_controllers/{serial_num}/dhcp_clients"
        params = {"reservation": False}
        return self.central.get(url, params)

    def get_vlan_info_by_gw(self, serial_num):
        return self.central.get(f"/monitoring/v1/mobility_controllers/{serial_num}/vlan")

    def get_uplink_info_by_gw(self, serial_num, timerange: str = "3H"):
        url = f"/monitoring/v1/mobility_controllers/{serial_num}/uplinks"
        params = {"timerange": timerange}
        return self.central.get(url, params)

    def get_uplink_tunnel_stats_by_gw(self, serial_num):
        url = f"/monitoring/v1/mobility_controllers/{serial_num}/uplinks/tunnel_stats"
        return self.central.get(url)

    def get_uplink_state_by_group(self, group):
        url = f"/monitoring/v1/mobility_controllers/uplinks/distribution?group={group}"
        header = {"authorization": f"Bearer {self.access_token}"}
        resp = self.get_call(url, header)
        pprint.pprint(resp)

    def get_all_sites(self):
        return self.central.get("/central/v2/sites")

    def get_site_details(self, site_id: Union[str, int]):
        return self.central.get(f"/central/v2/sites/{site_id}")

    def get_events_by_group(self, group):
        url = f"/monitoring/v1/events?group={group}"
        params = {"group": group}
        return self.central.get(url, params=params)

    def bounce_poe(self, serial_num, port):
        # url = f"/device_management/v2/device/{serial_num}/action/bounce_poe_port"
        # header = {
        #     "authorization": f"Bearer {self.access_token}",
        #     "Content-type": "application/json"
        # }
        # payload = {"port": port}
        # resp = requests.post(self.vars["base_url"] + url, json=payload, headers=header)
        url = f"/device_management/v1/device/{serial_num}/action/bounce_poe_port/port/{port}"
        header = {"authorization": f"Bearer {self.access_token}"}
        resp = requests.post(self.central.vars["base_url"] + url, headers=header)
        pprint.pprint(resp.json())

    def kick_users(self, serial_num, kick_all=False, mac=None, ssid=None):
        url = f"/device_management/v1/device/{serial_num}/action/disconnect_user"
        header = {
            "authorization": f"Bearer {self.access_token}",
            "Content-type": "application/json"
        }
        if kick_all:
            payload = {"disconnect_user_all": True}
        elif mac:
            payload = {"disconnect_user_mac": f"{mac}"}
        elif ssid:
            payload = {"disconnect_user_network": f"{ssid}"}
        else:
            payload = {}

        if payload:
            resp = requests.post(self.central.vars["base_url"] + url, headers=header, json=payload)
            pprint.pprint(resp.json())
        else:
            print("Missing Required Parameters")

    def get_task_status(self, task_id):
        return self.central.get(f"/device_management/v1/status/{task_id}")

    def add_dev(self, mac: str, serial_num: str):
        """
        {'code': 'ATHENA_ERROR_NO_DEVICE',
        'extra': {'error_code': 'ATHENA_ERROR_NO_DEVICE',
                'message': {'available_device': [],
                            'blocked_device': [],
                            'invalid_device': [{'mac': '20:4C:03:26:28:4c',
                                                'serial': 'CNF7JSP0N0',
                                                'status': 'ATHENA_ERROR_DEVICE_ALREADY_EXIST'}]}},
        'message': 'Bad Request'}
        """
        url = "/platform/device_inventory/v1/devices"
        payload = [
                {
                    "mac": mac,
                    "serial": serial_num
                }
            ]
        header = {
            "authorization": f"Bearer {self.central.access_token}",
            "Content-type": "application/json"
        }

        resp = requests.post(self.central.vars["base_url"] + url, headers=header, json=payload)
        pprint.pprint(resp.json())

    def verify_add_dev(self, mac: str, serial_num: str):
        """
        {
            'available_device': [],
            'blocked_device': [],
            'invalid_device': [
                                {
                                    'mac': '20:4C:03:26:28:4c',
                                    'serial': 'CNF7JSP0N0',
                                    'status': 'ATHENA_ERROR_DEVICE_ALREADY_EXIST'
                                }
                              ]
        }
        """
        url = "/platform/device_inventory/v1/devices/verify"
        payload = [
                {
                    "mac": mac,
                    "serial": serial_num
                }
            ]
        header = {
            "authorization": f"Bearer {self.central.access_token}",
            "Content-type": "application/json"
        }

        resp = requests.post(self.central.vars["base_url"] + url, headers=header, json=payload)
        pprint.pprint(resp.json())

    def move_dev_to_group(self, group: str, serial_num: Union[str, list]):
        url = "/configuration/v1/devices/move"
        if not isinstance(serial_num, list):
            serial_num = [serial_num]
        payload = {
                    "group": group,
                    "serials": serial_num
                  }
        header = {
            "authorization": f"Bearer {self.central.access_token}",
            "Content-type": "application/json"
        }

        resp = requests.post(self.central.vars["base_url"] + url, headers=header, json=payload)
        return resp.ok

    def caasapi(self, group_dev: str, cli_cmds: list = None):
        if ":" in group_dev and len(group_dev) == 17:
            key = "node_name"
        else:
            key = "group_name"

        url = "/caasapi/v1/exec/cmd"

        params = {
            "cid": self.central.vars.get('customer_id'),
            key: group_dev
        }

        header = {
            "authorization": f"Bearer {self.central.access_token}",
            "Content-type": "application/json"
        }

        payload = {"cli_cmds": cli_cmds or []}

        return requests.post(self.central.vars["base_url"] + url, params=params, headers=header, json=payload)
        # TODO use my resp generator


# t = CentralApi()
# t.get_ap()
# t.get_swarms_by_group("Branch1")
# t.get_swarm_details("fbe90101014332bf0dabfa5d2cf4ae7a0917a04127f864e047")
# t.get_wlan_clients(group="Branch1")
# t.get_wired_clients()
# t.get_wired_clients(group="Branch1")
# t.get_client_details("20:4c:03:30:4c:4c")
# t.get_certificates()
# t.get_template("WadeLab", "2930F-8")
# t.get_all_groups()
# t.get_dev_by_type("iap")
# t.get_dev_by_type("switch")
# t.get_dev_by_type("gateway")
# t.get_variablised_template("CN71HKZ1CL")
# t.get_ssids_by_group("Branch1")
# t.get_gateways_by_group("Branch1")
# t.get_group_for_dev_by_serial("CNHPKLB030")
# t.get_dhcp_client_info_by_gw("CNF7JSP0N0")
# t.get_vlan_info_by_gw("CNHPKLB030")
# t.get_uplink_info_by_gw("CNF7JSP0N0")
# t.get_uplink_tunnel_stats_by_gw("CNF7JSP0N0")
# t.get_uplink_state_by_group("Branch1")
# t.get_all_sites()
# t.get_site_details(10)
# t.get_events_by_group("Branch1")
# t.bounce_poe("CN71HKZ1CL", 2)
# t.kick_users("CNC7J0T0GK", kick_all=True)
# t.get_task_status(15983230525575)
# group_dev = "Branch1/20:4C:03:26:28:4C"
# cli_cmds = ["netdestination delme", "host 1.2.3.4", "!"]
# t.caasapi(group_dev, cli_cmds)
# mac = "20:4C:03:81:E8:FA"
# serial_num = "CNHPKLB030"
# t.add_dev(mac, serial_num)
# t.verify_add_dev(mac, serial_num)
# t.move_dev_to_group("Branch1", serial_num)


class BuildCLI:
    def __init__(self, data: dict = None, session=None, filename: str = None):
        filename = filename or _bulk_edit_file

        self.session = session
        self.dev_info = None
        if data:
            self.data = data
        else:
            self.data = self.get_bulkedit_data(filename)
        self.cmds = []
        self.build_cmds()

    def get_bulkedit_data(self, filename: str):
        cli_data = {}
        _common = {}
        _vlans = []
        _mac = "error"
        _exclude_start = ''
        with open(filename) as csv_file:
            csv_reader = csv.reader([line for line in csv_file.readlines() if not line.startswith('#')])

            csv_rows = [r for r in csv_reader]

            for data_row in csv_rows[1:]:
                vlan_data = {}
                for k, v in zip(csv_rows[0], data_row):
                    k = k.strip().lower().replace(' ', '_')
                    # print(f"{k}: {v}")
                    if k == "mac_address":
                        _mac = v
                        cli_data[v] = {}
                    elif k in ["group", "model", "hostname", "bg_peer_ip", "controller_vlan",
                               "zs_site_to_site_map_name", "source_fqdn"]:
                        _common[k] = v
                    elif k.startswith(("vlan", "dhcp", "domain", "dns", "vrrp", "access_port", "ppoe")):
                        if k == "vlan_id":
                            if vlan_data:
                                _vlans.append(vlan_data)
                            vlan_data = {k: v}
                        elif k.startswith("dns_server_"):
                            vlan_data["dns_servers"] = [v] if "dns_servers" not in vlan_data else \
                                                              [*vlan_data["dns_servers"], *[v]]
                        elif k.startswith("dhcp_default_router"):
                            vlan_data["dhcp_def_gws"] = [v] if "dhcp_def_gws" not in vlan_data else \
                                                               [*vlan_data["dhcp_def_gws"], *[v]]
                        elif k.startswith("dhcp_exclude_start"):
                            _exclude_start = v
                        elif k.startswith("dhcp_exclude_end"):
                            if _exclude_start:
                                _line = f"ip dhcp exclude-address {_exclude_start} {v}"
                                vlan_data["dhcp_excludes"] = [_line] if "dhcp_excludes" not in vlan_data else \
                                                                        [*vlan_data["dhcp_excludes"], *[_line]]
                                _exclude_start, _line = '', ''
                            else:
                                print(f"Validation Error DHCP Exclude End with no preceding start ({v})... Ignoring")
                        else:
                            vlan_data[k] = v

                _vlans.append(vlan_data)
                cli_data[_mac] = {"_common": _common, "vlans": _vlans}

        return cli_data

    def build_cmds(self):
        for dev in self.data:
            common = self.data[dev]["_common"]
            vlans = self.data[dev]["vlans"]
            _pretty_name = common.get('hostname', dev)
            print(f"Verifying {_pretty_name} is in Group {common['group']}...", end='')
            # group_devs = self.session.get_gateways_by_group(self.data[dev]["_common"]["group"])
            gateways = self.session.get_dev_by_type("gateway")
            self.dev_info = [_dev for _dev in gateways if _dev.get('macaddr', '').lower() == dev.lower()]
            if self.dev_info:
                self.dev_info = self.dev_info[0]
                if common["group"] == self.session.get_group_for_dev_by_serial(self.dev_info["serial"]):
                    print(' Confirmed', end='\n')
                else:
                    print(" it is *Not*", end="\n")
                    print(f"Moving {_pretty_name} to Group {common['group']}")
                    res = self.session.move_dev_to_group(common["group"], self.dev_info["serial"])
                    if not res:
                        print(f"Error Returned Moving {common['hostname']} to Group {common['group']}")

            print(f"Building cmds for {_pretty_name}")
            if common.get("hostname"):
                self.cmds += [f"hostname {common['hostname']}", "!"]

            for v in vlans:
                self.cmds += [f"vlan {v['vlan_id']}", "!"]
                if v.get("vlan_ip"):
                    if not v.get("vlan_subnet"):
                        print(f"Validation Error No subnet mask for VLAN {v['vlan_id']} ")
                        # TODO handle the error
                    self.cmds += [f"interface vlan {v['vlan_id']}", f"ip address {v['vlan_ip']} {v['vlan_subnet']}"]
                    # TODO should VLAN description also be vlan name - check what bulk edit does
                    if v.get("vlan_interface_description"):
                        self.cmds.append(f"description {v['vlan_interface_description']}")
                    if v.get("vlan_helper_addr"):
                        self.cmds.append(f"ip helper-address {v['vlan_helper_addr']}")
                    if v.get("vlan_interface_operstate"):
                        self.cmds.append(f"operstate {v['vlan_interface_operstate']}")
                    self.cmds.append("!")

                if v.get("pppoe_username"):
                    print("Warning PPPoE not supported by this tool yet")

                if v.get("access_port"):
                    if "thernet" not in v["access_port"] and not v["access_port"].startswith("g"):
                        _line = f"interface gigabitethernet {v['access_port']}"
                    else:
                        _line = f"interface {v['access_port']}"
                    self.cmds += [_line, f"switchport access vlan {v['vlan_id']}", "!"]

                if v.get("dhcp_pool_name"):
                    self.cmds.append(f"ip dhcp pool {v['dhcp_pool_name']}")
                    if v.get("dhcp_def_gws"):
                        for gw in v["dhcp_def_gws"]:
                            self.cmds.append(f"default-router {gw}")
                    if v.get("dns_servers"):
                        self.cmds.append(f"dns-server {' '.join(v['dns_servers'])}")
                    if v.get("domain_name"):
                        self.cmds.append(f"domain-name {v['domain_name']}")
                    if v.get("dhcp_network"):
                        if v.get("dhcp_mask"):
                            self.cmds.append(f"network {v['dhcp_network']} {v['dhcp_mask']}")
                        elif v.get("dhcp_network_prefix"):
                            self.cmds.append(f"network {v['dhcp_network']} /{v['dhcp_network_prefix']}")
                    self.cmds.append("!")

                if v.get("dhcp_excludes"):
                    # dhcp exclude lines are fully formatted as data is collected
                    for _line in v["dhcp_excludes"]:
                        self.cmds.append(_line)

                if v.get("vrrp_id"):
                    if v.get("vrrp_ip"):
                        self.cmds += [f"vrrp {v['vrrp_id']}", f"ip address {v['vrrp_ip']}", f"vlan {v['vlan_id']}"]
                        if v.get("vrrp_priority"):
                            self.cmds.append(f"priority {v['vrrp_priority']}")
                        self.cmds += ["no shutdown", "!"]
                    else:
                        print(f"Validation Error VRRP ID {v['vrrp_id']} VLAN {v['vlan_id']} No VRRP IP provided... Skipped")

                if v.get("bg_peer_ip"):
                    # _as = self.session.get_bgp_as()
                    # self.cmds.append(f"router bgp neighbor {v['bg_peer_ip']} as {_as}")
                    print("bgp peer ip Not Supported by Script yet")

                if v.get("zs_site_to_site_map_name") or v.get("source_fqdn"):
                    print("Zscaler Configuration Not Supported by Script Yet")


if __name__ == "__main__":
    cli = BuildCLI(session=CentralApi())
    for c in cli.cmds:
        print(c)
