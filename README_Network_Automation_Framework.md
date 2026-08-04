Network Automation Framework (Ansible + Jinja)

Overview
This repository contains a robust, scalable NetDevOps automation framework designed specifically for managing Cisco IOS devices. Built on Ansible and Jinja2 templating, this tool abstracts raw CLI configuration into structured YAML data models, allowing network engineers to deploy infrastructure as code.
The framework is highly modular and supports safe, idempotent execution, automated backups, and structured template rendering for tasks like VLAN provisioning and SVI configurations. It is also optimized to act as the execution engine for AI-assisted coding agents (such as Cline in VS Code), allowing operators to generate network state files via natural language prompts.

Key Features

•	Idempotent Execution: Leverages the cisco.ios.ios_config and cisco.ios.ios_vlans modules to compare target configurations against the device's running-config, ensuring commands are only pushed if changes are required.

•	Automated Backups: Every configuration push automatically saves a timestamped copy of the current running-config to a local backup/ directory before any changes are applied.

•	Two-Stage Jinja Templating: Uses ansible.builtin.template with delegate_to: localhost to render device-specific configurations into local text files before securely transporting them to the switches.

•	Safe Dry-Runs: Fully supports Ansible's --check --diff flags, allowing operators to visually review proposed additions (+) and subtractions (-) without modifying the actual switch state.

•	Persistent State Management: Features the save_when: changed directive, which automatically issues a copy running-config startup-config only when the automation engine actually modifies the device.

•	Legacy SSH Compatibility: Injects parameters like KexAlgorithms=+diffie-hellman-group14-sha1 and HostKeyAlgorithms=+ssh-rsa natively through group_vars to ensure secure connections to older Catalyst platforms.
Prerequisites and Installation
To run this automation framework, the control node (e.g., Ubuntu Linux) requires Python and Ansible.

1. Core System Dependencies
Install the required packages using the following commands:
Bash
sudo apt update 
sudo apt install -y python3 python3-pip pipx sshpass
pipx ensurepath

2. Install Ansible & Libraries
Bash
pipx install --include-deps ansible
pipx inject ansible paramiko
pipx inject ansible ansible-pylibssh

3. Install Required Ansible Collections
Bash
ansible-galaxy collection install cisco.ios 
ansible-galaxy collection install ansible.netcommon
Directory Architecture
This project strictly follows Ansible best practices for decoupling logic from data:
Plaintext
ansible-cisco/
├── inventory.ini                 # Defines devices and group mappings 
├── group_vars/ 
│   └── cisco_ios.yml             # SSH credentials, legacy crypto arguments, and network_cli parameters 
├── host_vars/ 
│   ├── cctv_sw1.yml              # Device-specific YAML parameters (e.g., VLAN arrays) 
│   └── cctv_sw2.yml 
├── templates/ 
│   ├── switch_config.j2          # Blueprint for full configuration generation
│   └── svi_descriptions.j2       # Blueprint for specific interface setups
├── backup/                       # Automated storage for pre-deployment running-configs
└── playbooks/
    ├── test-connect.yml          # Connectivity verification using ios_command
    ├── deploy_vlans.yml          # Core execution playbook for VLAN generation
    └── push-config.yml           # Pushes flat configuration files
Usage Guide

1. Verify Connectivity
Before making changes, verify that the Ansible control node can securely authenticate with your network inventory:
Bash
ansible-playbook -i inventory.ini test-connect.yml
This playbook utilizes cisco.ios.ios_command to run show version and returns the output to validate SSH functionality.

2. Define Variables
Add device-specific data to your host_vars files. For example, in host_vars/cctv_sw1.yml:
YAML
hostname: CCTV-SW1
vlans:
  - vlan_id: 10
    name: CAMERAS
    svi_description: CCTV cameras users

3. Dry-Run / Preview Changes
Always simulate configuration deployments to catch formatting or syntax errors. The --check --diff flags will intercept the playbook and output a color-coded delta mapping:
Bash
ansible-playbook -i inventory.ini deploy_vlans.yml --check --diff

4. Deploy Configuration
If the dry-run looks accurate, execute the final playbook to modify the switches and save the startup-config:
Bash
ansible-playbook -i inventory.ini deploy_vlans.yml
AI Agent Integration (Optional)
This repository structure is optimized to pair with local AI coding agents like Cline (VS Code) or OpenHands alongside a local LLM runner like Ollama.
Example AI Workflow:
1.	Provide a natural language prompt: "Create VLAN 70 for cameras on cctv_sw2".
2.	The agent parses the request and updates host_vars/cctv_sw2.yml.
3.	The agent generates the necessary Jinja templating.
4.	The agent prompts you for approval before running ansible-playbook --check --diff.

