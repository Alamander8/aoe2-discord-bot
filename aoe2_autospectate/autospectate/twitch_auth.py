import requests
import time
import logging


def get_device_code(client_id: str):
    response = requests.post('https://id.twitch.tv/oauth2/device', data={
        'client_id': client_id,
        'scope': 'chat:read chat:edit'
    })
    return response.json()

def get_chat_token(client_id: str, client_secret: str):
    """Gets token for chat bot operations"""
    try:
        # Get user access token with needed scopes for chat
        response = requests.post('https://id.twitch.tv/oauth2/token', data={
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials',
            'scope': 'chat:read chat:edit'
        })
        response.raise_for_status()
        token_data = response.json()
        
        # Validate token
        headers = {
            'Authorization': f'Bearer {token_data["access_token"]}',
            'Client-Id': client_id
        }
        
        validate_response = requests.get('https://id.twitch.tv/oauth2/validate', headers=headers)
        if validate_response.status_code != 200:
            raise Exception("Token validation failed")
            
        logging.info("Chat token validation successful")
        return f"oauth:{token_data['access_token']}"  # Return with oauth: prefix
        
    except Exception as e:
        logging.error(f"Failed to get chat token: {e}")
        raise

def get_app_access_token(client_id: str, client_secret: str):
    try:
        response = requests.post('https://id.twitch.tv/oauth2/token', data={
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials',
            'scope': 'chat:read chat:edit'  # Add required scopes
        })
        response.raise_for_status()  # Raise exception for bad status
        token_data = response.json()
        logging.info("Successfully obtained Twitch token")
        return token_data['access_token']
    except Exception as e:
        logging.error(f"Failed to get Twitch token: {e}")
        raise

def poll_for_access_token(client_id: str, device_code: str):
    while True:
        try:
            response = requests.post('https://id.twitch.tv/oauth2/token', data={
                'client_id': client_id,
                'device_code': device_code,
                'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
            })
            
            if response.status_code == 200:
                return response.json()['access_token']
            
            time.sleep(5)  # Wait before polling again
            
        except Exception as e:
            print(f"Error polling for token: {e}")
            time.sleep(5)