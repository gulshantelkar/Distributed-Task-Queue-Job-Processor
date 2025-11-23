"""
WebSocket consumers for real-time job updates.
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)


class JobUpdateConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time job status updates.
    
    Clients connect to: ws://localhost:8000/ws/jobs/<tenant_id>/
    
    Receives updates when:
    - Job status changes
    - New job created
    - Job completed/failed
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        # Get tenant_id from URL route
        self.tenant_id = self.scope['url_route']['kwargs']['tenant_id']
        self.room_group_name = f'tenant_{self.tenant_id}'
        

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        logger.info(f"WebSocket connected: tenant={self.tenant_id}")
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to job updates',
            'tenant_id': self.tenant_id
        }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        logger.info(f"WebSocket disconnected: tenant={self.tenant_id}, code={close_code}")
    
    async def receive(self, text_data):
        """
        Receive message from WebSocket.
        Can be used for ping/pong or subscribing to specific job types.
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'ping':
                # Respond to ping
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat()
                }))
            
            elif message_type == 'subscribe':
                job_types = data.get('job_types', [])
                await self.send(text_data=json.dumps({
                    'type': 'subscribed',
                    'job_types': job_types
                }))
        
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
    
    async def job_update(self, event):
        """
        Receive job update from room group.
        Called when a job status changes.
        """
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'job_update',
            'job_id': event['job_id'],
            'status': event['status'],
            'job_type': event.get('job_type'),
            'timestamp': timezone.now().isoformat()
        }))
    
    async def job_created(self, event):
        """
        Receive job created notification from room group.
        """
        await self.send(text_data=json.dumps({
            'type': 'job_created',
            'job_id': event['job_id'],
            'job_type': event.get('job_type'),
            'timestamp': timezone.now().isoformat()
        }))

