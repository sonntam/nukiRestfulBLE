from flask import Flask, request, jsonify
from flasgger import Swagger
import json
import base64
import os
import pyNukiBT
import random
import threading
import logging
import asyncio
from typing import List, Dict, Tuple
from bleak import BleakScanner
from bleak import BleakClient
from bleak.backends.device import BLEDevice
from nacl.public import PrivateKey
from job_queue import JobQueue

swagger_config = {
    "headers": [],
    "openapi": "3.0.2",
    "title": "Nuki BLE API",
    "version": '1.0',
    "termsOfService": "",
    "static_url_path": "/",
    "swagger_ui": True,
    'specs': [
        {
            'endpoint': 'apispec',
            'route': '/apispec.json'
        }
    ],
    "description": "This is the description of nukiRestful, a REST API to control Nuki locks via Bluetooth Low-Energy BLE. It is powered by Flask, pyNukiBT, bleak and Flasgger",
}

# Flask & Swaggedr
app = Flask(__name__)
swagger = Swagger(app, config=swagger_config, merge=True)

# Config
config = {}
configPath = "./settings/config.json"

# Logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Other globals
scanner = BleakScanner()
job_queue = JobQueue()

@app.get('/listPaired')
async def listPaired():
    """
    List paired devices and update their info
    ---
    tags:
        - Pairing
    responses:
        200:
            description: Successfully listed and updated paired devices
            schema:
                type: object
                properties:
                    message:
                        type: string
                        description: Message indicating the number of registered devices
                    devices:
                        type: array
                        items:
                            type: object
                            properties:
                                address:
                                    type: string
                                    description: MAC address of the device
                                isReachable:
                                    type: boolean
                                    description: Whether the device is reachable
                                name:
                                    type: string
                                    description: Name of the device
                                id:
                                    type: string
                                    description: ID of the device
        500:
            description: Error while listing paired devices
    """

    try:
        devices = await job_queue.submit_job(async_get_registered_devices, config=config)
            
        return jsonify({
            'message': f'Found {len(devices)} registered devices',
            'devices': devices
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

async def async_get_registered_devices(config: Dict[str, any]):
    devices = []
    for pairedDevice in config['pairedDevices']:
        address = pairedDevice['address']
        _, device, ble_device = await async_get_paired_device( address, config )

            # Update name and id if possible
        if ble_device != None:
            logger.info(f"Updating info of device {address}...")
            await device.connect()
            await device.update_state()
            update_and_save_device_info(device, address, config)
            await device.disconnect()

        devices.append({
                'address': address,
                'isReachable': ble_device != None,
                'name': pairedDevice['name'],
                'id': pairedDevice['id']
            })
        
    return devices

@app.post('/pair')
async def pair():
    """
    Pair a new device
    ---
    tags:
        - Pairing
    parameters:
    - name: address
      in: body
      type: string
      required: true
      description: The MAC address of the device to pair
      schema:
      type: object
      properties:
          address:
              type: string
              description: The MAC address
    responses:
        200:
            description: Device registered successfully
        400:
            description: MAC address is missing
        500:
            description: Error while pairing with the device
    """

    try:
        # Get JSON data from the request
        data = request.get_json()
        
        # Extract the MAC address from the JSON data
        address = data.get('address')
        
        # Check if the address is provided
        if not address:
            return jsonify({'error': 'MAC address is missing'}), 400
        
        # Perform your logic here with the MAC address
        logger.info(f"Received MAC address: {address}")
        
        ble_device = await job_queue.submit_job(scanner.find_device_by_address, device_identifier=address)
        #ble_device = await scanner.find_device_by_address(device_identifier=address)

        if ble_device == None:
            raise ConnectionError(f"Device with address {address} is not reachable.")

        # Try to register device, get auth info and save to config
        client_type = pyNukiBT.NukiConst.NukiClientType.BRIDGE
        
        device = pyNukiBT.NukiDevice(address=address, auth_id=None, nuki_public_key=None,
            bridge_public_key=base64.b64decode(config['publicKey']), 
            bridge_private_key=base64.b64decode(config['privateKey']),
            app_id=config['appId'], name=config['appName'], client_type=client_type, ble_device=ble_device, 
            get_ble_device=lambda addr: scanner.find_device_by_address(address))
        
        await job_queue.submit_job( device.connect )

        pairingResult = await job_queue.submit_job( device.pair )

        config['pairedDevices'] = replace_or_add_entry_by_address(
            config['pairedDevices'], 
            {
                'address': address,
                'authId': pairingResult['auth_id'],
                'devicePublicKey': pairingResult['nuki_public_key'],
            }
        )
        
        save_config(configPath, config)

        await job_queue.submit_job( device.disconnect )
    
        # Return a success response
        return jsonify({'message': 'Device registered successfully'}), 200
    
    except pyNukiBT.NukiErrorException as nex:
        return jsonify({'error': 'Error while pairing with Nuki device. Make sure the device is in pairing mode (press the button for 6 seconds) and that the address is correct.'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.post('/unpair')
async def unpair():
    """
    Unpair a device
    ---
    tags:
        - Pairing
    parameters:
      - name: address
        in: body
        type: string
        required: true
        description: The MAC address of the device to unpair
        schema:
          type: object
          properties:
            address:
              type: string
              description: The MAC address
    responses:
      200:
        description: Device unpaired successfully
      400:
        description: MAC address is missing or device not paired
      500:
        description: Error while unpairing the device
    """
    try:
        data = request.get_json()
        address = data.get('address')
        
        if not address:
            return jsonify({'error': 'MAC address is missing'}), 400
        
        paired_devices = [device for device in config['pairedDevices'] if device.get('address') == address]
        
        if not paired_devices:
            return jsonify({'error': f'Device with address {address} is not paired'}), 400

        config['pairedDevices'] = [device for device in config['pairedDevices'] if device.get('address') != address]

        save_config(configPath, config)
        
        return jsonify({'message': 'Device unpaired successfully'}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.get('/scan')
async def scan():
    """
    Scan for nearby Nuki devices
    ---
    tags:
        - Pairing
    responses:
        200:
            description: Successfully scanned and found possible Nuki devices
            schema:
                type: object
                properties:
                    message:
                        type: string
                        description: Message indicating the number of devices found
                    devices:
                        type: array
                        items:
                            type: object
                            properties:
                                name:
                                    type: string
                                    description: Name of the device
                                address:
                                    type: string
                                    description: MAC address of the device
        500:
            description: Error while scanning for devices
    """

    try:
        
        await job_queue.submit_job( scanner.stop )
        devices = await job_queue.submit_job( scanner.discover )
        deviceCandidates = []
        for device in devices:
            if (device.name and device.name.startswith("Nuki")) or (device.address and device.address.upper().startswith('52:D2:72:')):
                logger.info(f"Found possible Nuki device {device.name}, Address: {device.address}, RSSI: {device.rssi}")
                deviceCandidates.append(device)
        return jsonify({'message': f"Found {len(deviceCandidates)} possible Nuki devices", 
                        'devices': list(map(lambda x: { 'name': x.name, 'address': x.address },deviceCandidates))}
        ), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.post('/lock')
async def lock():
    """
    Lock a paired device
    ---
    tags:
        - Control
    parameters:
    - name: address
      in: body
      type: string
      required: true
      description: The MAC address of the device to lock
      schema:
      type: object
      properties:
          address:
              type: string
              description: The MAC address
    responses:
        200:
            description: Locked successfully
        400:
            description: MAC address is missing or device not paired
        500:
            description: Error while locking the device
    """

    try:
        # Get JSON data from the request
        address: str = request.get_json()['address']
        
        pairedDevice, device, ble_device = await job_queue.submit_job( async_get_paired_device, address=address, config=config)

        if ble_device == None:
            raise ConnectionError(f"Device with address {address} is not reachable.")
        
        await job_queue.submit_job( device.connect )
        await job_queue.submit_job( device.update_state )
        await job_queue.submit_job( device.lock )
        await job_queue.submit_job( device.disconnect )

        return jsonify({'message': 'Locked successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.post('/unlock')
async def unlock():
    """
    Unlock a paired device
    ---
    tags:
        - Control
    parameters:
    - name: address
      in: body
      type: string
      required: true
      description: The MAC address of the device to unlock
      schema:
      type: object
      properties:
          address:
              type: string
              description: The MAC address
    responses:
        200:
            description: Unlocked successfully
        400:
            description: MAC address is missing or device not paired
        500:
            description: Error while unlocking the device
    """

    try:
        # Get JSON data from the request
        address: str = request.get_json()['address']
        
        pairedDevice, device, ble_device = await job_queue.submit_job( async_get_paired_device, address=address, config=config)
        
        if ble_device == None:
            raise ConnectionError(f"Device with address {address} is not reachable.")

        await job_queue.submit_job( device.connect )
        await job_queue.submit_job( device.update_state )
        await job_queue.submit_job( device.unlock )
        await job_queue.submit_job( device.disconnect )

        return jsonify({'message': 'Unlocked successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.post('/unlatch')
async def unlatch():
    """
    Unlatch a paired device
    ---
    tags:
        - Control
    parameters:
    - name: address
      in: body
      type: string
      required: true
      description: The MAC address of the device to unlatch
      schema:
          type: object
          properties:
              address:
                  type: string
                  description: The MAC address
    responses:
        200:
            description: Unlatched successfully
        400:
            description: MAC address is missing or device not paired
        500:
            description: Error while unlatching the device
    """

    try:
        # Get JSON data from the request
        address: str = request.get_json()['address']
        
        pairedDevice, device, ble_device = await job_queue.submit_job( async_get_paired_device, address=address, config=config)
        
        if ble_device == None:
            raise ConnectionError(f"Device with address {address} is not reachable.")

        await job_queue.submit_job( device.connect )
        await job_queue.submit_job( device.update_state )
        await job_queue.submit_job( device.unlatch )
        await job_queue.submit_job( device.disconnect )

        return jsonify({'message': 'Unlatched successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.get('/state')
async def state():
    """
    Get the state of a paired device
    ---
    tags:
        - Status
    parameters:
    - name: address
      in: query
      type: string
      required: true
      description: The MAC address of the device
    responses:
        200:
            description: Successfully retrieved device state
            schema:
                type: object
                properties:
                    name:
                        type: string
                        description: Name of the device
                    id:
                        type: string
                        description: ID of the device
                    firmwareVersion:
                        type: string
                        description: Firmware version of the device
                    hardwareRevision:
                        type: string
                        description: Hardware revision of the device
                    pairingEnabled:
                        type: boolean
                        description: Whether pairing is enabled
                    lockState:
                        type: string
                        description: Current lock state of the device
                    batteryPercentage:
                        type: integer
                        description: Battery percentage of the device
                    deviceType:
                        type: string
                        description: Type of the device
                    nightmodeActive:
                        type: boolean
                        description: Whether night mode is active
                    lastAction:
                        type: string
                        description: Last lock action performed
                    doorSensorState:
                        type: string
                        description: State of the door sensor
                    deviceState:
                        type: string
                        description: Overall state of the device
                    help:
                        type: object
                        properties:
                            lockStateValues:
                                type: string
                                description: Possible lock state values
                            deviceTypeValues:
                                type: string
                                description: Possible device type values
                            lastActionValues:
                                type: string
                                description: Possible last action values
                            doorSensorStateValues:
                                type: string
                                description: Possible door sensor state values
                            deviceStateValues:
                                type: string
                                description: Possible device state values
        400:
            description: MAC address is missing or device not paired
        500:
            description: Error while retrieving the device state
    """
    try:
        # Your logic for getting the state goes here
        # Get JSON data from the request
        address: str = request.args.get('address')
        
        pairedDevice, device, ble_device = await job_queue.submit_job( async_get_paired_device, address=address, config=config)

        if ble_device == None:
            raise ConnectionError(f"Device with address {address} is not reachable.")

        await job_queue.submit_job( device.connect )
        await job_queue.submit_job( device.update_state )
        update_and_save_device_info(device, address, config)
        await job_queue.submit_job( device.disconnect )

        state = {
            'name': pairedDevice['name'],
            'id': pairedDevice['id'],
            'firmwareVersion': '.'.join([str(e) for e in device.config.firmware_version]),
            'hardwareRevision': '.'.join([str(e) for e in device.config.hardware_revision]),
            'pairingEnabled': device.config.pairing_enabled,
            'lockState': str(device.keyturner_state.lock_state),
            'batteryPercentage': device.battery_percentage,
            'deviceType': str(device.device_type),
            'nightmodeActive': device.keyturner_state.nightmode_active,
            'lastAction': str(device.keyturner_state.last_lock_action),
            'doorSensorState': str(device.keyturner_state.door_sensor_state),
            'deviceState': str(device.keyturner_state.nuki_state),
            'help': {
                'lockStateValues': ', '.join([e for e in pyNukiBT.NukiLockConst.LockState.ksymapping.values()]),
                'deviceTypeValues:': ', '.join([e for e in pyNukiBT.NukiLockConst.NukiDeviceType.ksymapping.values()]),
                'lastActionValues': ', '.join([e for e in pyNukiBT.NukiLockConst.LockAction.ksymapping.values()]),
                'doorSensorStateValues': ', '.join([e for e in pyNukiBT.NukiLockConst.DoorsensorState.ksymapping.values()]),
                'deviceStateValues': ', '.join([e for e in pyNukiBT.NukiLockConst.State.ksymapping.values()])
            }
        }

        del device
        del ble_device

        return jsonify(state), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def page_not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404

def default_config():

    keypair = PrivateKey.generate()
    public_key = base64.b64encode(bytes(keypair.public_key)).decode('utf-8')
    private_key = base64.b64encode(bytes(keypair)).decode('utf-8')

    return {
        'appName': 'pyNukiServer',
        'appId': random.getrandbits(32),
        'privateKey': private_key,
        'publicKey': public_key,
        'pairedDevices': [],
        'apiPort': 51001,
        'apiBindAddress': '0.0.0.0'
    }

def load_config(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} does not exist. Returning default dictionary.")
        return default_config()

    with open(file_path, 'r') as file:
        try:
            config = json.load(file)

            # Add missing fields from default config and remove superfluous ones
            config = sync_dictionaries(default_config(), config)

            return config
        except json.JSONDecodeError:
            print(f"Error decoding JSON from file {file_path}. Returning default config.")
            return default_config()

def save_config(file_path, config):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as file:
        json.dump(config, file, indent=4)

def sync_dictionaries(reference_dict, target_dict):
    # Remove keys not in reference_dict
    target_dict = {k: v for k, v in target_dict.items() if k in reference_dict}
    
    # Add keys from reference_dict that are not in target_dict
    for k, v in reference_dict.items():
        if k not in target_dict:
            target_dict[k] = v

    return target_dict

def replace_or_add_entry_by_address(data_list: List[any], new_entry: Dict[str, any]) -> List[any]:
    for i, item in enumerate(data_list):
        if item.get('address').upper() == new_entry['address'].upper():
            data_list[i] = new_entry
            return data_list
        
    data_list.append(new_entry)

    return data_list

def update_and_save_device_info(device: pyNukiBT.NukiDevice, address: str, config: Dict[str, any]):
    
    # Get Paired device entry from config
    # Check if the address is provided
    if not address:
        raise ValueError('MAC address is missing')
    
    # Check if address is paired
    pairedDevice = next((item for item in config['pairedDevices'] if item.get('address').lower() == address.lower()), None)
    if pairedDevice == None:
        raise LookupError(f'Device with address {address} has not been paired yet.')

    pairedDevice['name'] = device.config.name
    pairedDevice['id'] = device.config.nuki_id

    save_config(configPath, config)

async def async_get_paired_device(address: str, config: Dict[str, any]) -> Tuple[dict,pyNukiBT.NukiDevice,BLEDevice]:
    # Check if the address is provided
    if not address:
        raise ValueError('MAC address is missing')
        
    # Check if address is paired
    pairedDevice = next((item for item in config['pairedDevices'] if item.get('address').lower() == address.lower()), None)
    if pairedDevice == None:
        raise LookupError(f'Device with address {address} has not been paired yet.')

    ble_device: BLEDevice = await BleakScanner.find_device_by_address(address)
    device: pyNukiBT.NukiDevice = pyNukiBT.NukiDevice(address=address, 
            auth_id=base64.b64decode(pairedDevice['authId']), 
            nuki_public_key=base64.b64decode(pairedDevice['devicePublicKey']),
            bridge_public_key=base64.b64decode(config['publicKey']), 
            bridge_private_key=base64.b64decode(config['privateKey']),
            app_id=config['appId'], name=config['appName'], client_type=pyNukiBT.NukiConst.NukiClientType.BRIDGE, 
            ble_device=ble_device, 
            get_ble_device=lambda addr: BleakScanner.find_device_by_address(address))

    return pairedDevice, device, ble_device

if __name__ == '__main__':
    config = load_config(configPath)
    save_config(configPath, config)
    job_queue.start()
    #app.run(debug=True, port=config['apiPort'])
    app.run(host=config['apiBindAddress'], port=config['apiPort'])

