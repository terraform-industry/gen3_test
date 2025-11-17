"""Configuration loader for MK1_AWE devices.yaml"""

import os
import yaml


def load_config(config_path=None):
    """Load and parse devices.yaml configuration file.
    
    Args:
        config_path: Optional path to config file. Defaults to ../config/devices.yaml
        
    Returns:
        dict: Parsed configuration with keys: devices, modules, gas_reference, system, telegraf
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    if config_path is None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, '..', 'config', 'devices.yaml')
    
    config_path = os.path.abspath(config_path)
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return config


def get_rlm_endpoint():
    """Get RLM relay module IP and port.
    
    Returns:
        tuple: (ip, port) for RLM_30ch device
    """
    config = load_config()
    rlm = config['devices']['RLM_30ch']
    return (rlm['ip'], rlm['port'])


def get_bga_ports():
    """Get BGA HTTP bridge ports.
    
    Returns:
        dict: {device_id: http_port} for BGA01 and BGA02
    """
    config = load_config()
    return {
        'BGA01': config['modules']['BGA01']['http_port'],
        'BGA02': config['modules']['BGA02']['http_port']
    }


def get_psu_ips():
    """Get all PSU IP addresses from MM01 and MM02.
    
    Returns:
        list: IP addresses for PSU01-PSU10
    """
    config = load_config()
    ips = []
    for channel in config['devices']['MM01_8ch']['channels']:
        ips.append(channel['ip'])
    for channel in config['devices']['MM02_8ch']['channels']:
        if channel['name'].startswith('PSU'):
            ips.append(channel['ip'])
    return ips


def get_influx_params():
    """Get InfluxDB connection parameters.
    
    Returns:
        dict: url, org, bucket from system section
    """
    config = load_config()
    system = config['system']
    return {
        'url': system['influxdb_url'],
        'org': system['influxdb_org'],
        'bucket': system['influxdb_bucket']
    }


def get_psu_config():
    """Get PSU control configuration.
    
    Returns:
        dict: mode and mode-specific config (gen2 or mk1)
    """
    config = load_config()
    return config['psu_control']


def get_sensor_conversions():
    """Get analog input sensor conversion parameters.
    
    Returns:
        dict: Channel-specific conversion configs for Gen3 analog inputs
    """
    config = load_config()
    
    # Gen3: Read from NI_cDAQ_Analog (slot_1 and slot_4)
    conversions = {}
    
    try:
        ni_analog = config['modules']['NI_cDAQ_Analog']
        
        # Slot 1 channels (AI01-AI08)
        for channel_id, channel_config in ni_analog.get('slot_1', {}).items():
            conversions[channel_id] = {
                'min_mA': channel_config['range_min'] * 1000,  # Convert A to mA
                'max_mA': channel_config['range_max'] * 1000,
                'min_eng': channel_config['eng_min'],
                'max_eng': channel_config['eng_max'],
                'unit': channel_config['eng_unit'],
                'label': channel_config['name']
            }
        
        # Slot 4 channels (AI09-AI16)
        for channel_id, channel_config in ni_analog.get('slot_4', {}).items():
            conversions[channel_id] = {
                'min_mA': channel_config['range_min'] * 1000,
                'max_mA': channel_config['range_max'] * 1000,
                'min_eng': channel_config['eng_min'],
                'max_eng': channel_config['eng_max'],
                'unit': channel_config['eng_unit'],
                'label': channel_config['name']
            }
    except KeyError:
        # Fallback: Return empty dict if Gen3 structure not found
        pass
    
    return conversions

