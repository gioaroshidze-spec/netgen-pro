import os
from routers.auth import decrypt_secret

def get_netmiko_params(device, is_human=False):
    """
    Builds a standard dictionary of Netmiko connection parameters.
    Injects the +ct suffix for MikroTik devices to disable formatting,
    UNLESS explicitly requested by a human operator (e.g., Web CLI).
    """
    os_type = (device.os_type or "cisco").lower()
    
    # Map OS to Netmiko's exact device_type
    if os_type == 'mikrotik': 
        netmiko_os = 'mikrotik_routeros'
    elif os_type in ['hpe', 'aruba']: 
        netmiko_os = 'hp_procurve'
    elif os_type in ['alcatel', 'alcatel-lucent']: 
        netmiko_os = 'alcatel_aos'
    else: 
        netmiko_os = 'cisco_ios'

    # The MikroTik Terminal Hallucination Bypass
    safe_username = device.username
    if os_type == "mikrotik" and not is_human:
        safe_username = f"{device.username}+ct"

    params = {
        'device_type': netmiko_os,
        'host': device.ip_address,
        'username': safe_username,
        'password': decrypt_secret(device.encrypted_password),
    }

    # Vendor-specific connection tuning
    if os_type == 'mikrotik' and not is_human:
        params['fast_cli'] = False
        params['conn_timeout'] = 20
        params['auth_timeout'] = 20
        params['global_delay_factor'] = 2
    else:
        params['fast_cli'] = True

    return params


def get_ansible_inventory_vars(device):
    """
    Builds a dictionary of Ansible inventory variables for dynamic playbooks.
    Injects the +cte1024w suffix for MikroTik devices to prevent automation crashes.
    """
    os_type = (device.os_type or "cisco").lower()
    
    # Map OS to Ansible's exact network_os collection
    if os_type == "aruba": ansible_os = "arubanetworks.aoscx.aoscx"
    elif os_type == "hpe": ansible_os = "community.network.aruba"
    elif os_type == "mikrotik": ansible_os = "community.routeros.routeros"
    elif os_type in ["alcatel", "alcatel-lucent"]: ansible_os = "community.network.alcatel_aos"
    else: ansible_os = "cisco.ios.ios"
    
    # Extreme MikroTik anti-formatting trick for Ansible
    safe_username = f"{device.username}+cte1024w" if os_type == "mikrotik" else device.username
    
    vars_dict = {
        "ansible_host": device.ip_address,
        "ansible_user": safe_username,
        "ansible_password": decrypt_secret(device.encrypted_password),
        "ansible_network_os": ansible_os,
        "ansible_connection": "network_cli",
        "ansible_ssh_common_args": "-o StrictHostKeyChecking=no"
    }

    # Privilege Escalation (MikroTik doesn't use standard enable)
    if os_type != "mikrotik":
        vars_dict["ansible_become"] = "yes"
        vars_dict["ansible_become_method"] = "enable"
    else:
        vars_dict["ansible_become"] = "no"

    return vars_dict