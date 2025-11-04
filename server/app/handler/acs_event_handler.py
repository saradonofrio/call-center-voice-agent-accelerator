"""
Handler for processing ACS (Azure Communication Services) call and callback events.

This module manages the lifecycle of phone calls through Azure Communication Services:
- Receiving and validating incoming call events
- Answering calls with media streaming configuration
- Processing call lifecycle events (connected, disconnected, media streaming)

The handler integrates with Voice Live API via WebSocket for bidirectional audio streaming.
"""

import json
import logging
import uuid
from urllib.parse import urlencode, urlparse, urlunparse

from azure.communication.callautomation import (AudioFormat,
                                                MediaStreamingAudioChannelType,
                                                MediaStreamingContentType,
                                                MediaStreamingOptions,
                                                StreamingTransportType)
from azure.communication.callautomation.aio import CallAutomationClient
from azure.eventgrid import EventGridEvent, SystemEventNames
from quart import Response

logger = logging.getLogger(__name__)


class AcsEventHandler:
    """
    Handles ACS event processing and call answering logic.
    
    This class manages the Azure Communication Services integration:
    - Initializes ACS client with connection string
    - Processes incoming call events from EventGrid
    - Configures and answers calls with bidirectional audio streaming
    - Handles call lifecycle callbacks (connected, disconnected, media events)
    
    Architecture:
        EventGrid → process_incoming_call() → answer_call() → WebSocket Audio Stream
        ACS Callbacks → process_callback_events() → Logging and monitoring
    """

    def __init__(self, config):
        """
        Initialize the ACS event handler.
        
        Args:
            config (dict): Configuration dictionary containing:
                - ACS_CONNECTION_STRING: Azure Communication Services connection string
        """
        # Initialize async ACS client for call automation
        self.acs_client = CallAutomationClient.from_connection_string(
            config["ACS_CONNECTION_STRING"]
        )

    async def process_incoming_call(self, events: list, host_url, config):
        """
        Process incoming call events from Azure EventGrid.
        
        This method handles two types of requests:
        1. EventGrid subscription validation (handshake)
        2. Incoming call events (actual phone calls)
        
        For incoming calls, the method:
        - Extracts caller information (phone number or raw ID)
        - Constructs callback and WebSocket URLs for the call
        - Configures media streaming with PCM audio format
        - Answers the call with bidirectional audio streaming
        
        Args:
            events (list): List of EventGrid event dictionaries
            host_url (str): Base URL of the server (e.g., https://example.com)
            config (dict): Configuration dictionary containing:
                - ACS_DEV_TUNNEL: Optional dev tunnel URL for local development
                
        Returns:
            Response: 
                - 200 OK for both validation and successful call answer
                - 400 Bad Request if no valid events processed
                
        EventGrid Validation Flow:
            EventGrid sends validation event → Return validation code → Subscription confirmed
            
        Incoming Call Flow:
            Phone call received → Extract caller ID → Configure media streaming →
            Answer call with WebSocket URL → Audio stream established
        """
        logger.info("incoming event data")

        # Process each event in the batch
        for event_dict in events:
            # Convert dictionary to EventGridEvent object
            event = EventGridEvent.from_dict(event_dict)
            logger.info("incoming event data --> %s", event.data)

            # ============================================================
            # EVENTGRID SUBSCRIPTION VALIDATION
            # ============================================================
            # Handle subscription validation (EventGrid handshake)
            # This is required when first setting up the EventGrid subscription
            if (
                event.event_type
                == SystemEventNames.EventGridSubscriptionValidationEventName
            ):
                logger.info("Validating subscription")
                validation_code = event.data["validationCode"]
                return Response(
                    response=json.dumps({"validationResponse": validation_code}),
                    status=200,
                )

            # ============================================================
            # INCOMING CALL EVENT PROCESSING
            # ============================================================
            # Process actual incoming phone call events
            if event.event_type == "Microsoft.Communication.IncomingCall":
                logger.info("Incoming call received: data=%s", event.data)

                # Extract caller information from event data
                caller_info = event.data["from"]
                
                # Extract caller ID based on identifier type
                # Phone calls use phoneNumber, other identifiers use rawId
                caller_id = (
                    caller_info["phoneNumber"]["value"]
                    if caller_info["kind"] == "phoneNumber"
                    else caller_info["rawId"]
                )

                logger.info("incoming call handler caller id: %s", caller_id)
                
                # Get incoming call context for answering the call
                incoming_call_context = event.data["incomingCallContext"]
                
                # Prepare query parameters with caller ID for callback URLs
                query_parameters = urlencode({"callerId": caller_id})
                
                # Generate unique GUID for tracking this call
                guid = uuid.uuid4()

                # ============================================================
                # CONSTRUCT CALLBACK URL
                # ============================================================
                # Determine base URL for callbacks
                # Use dev tunnel URL if configured (for local development)
                # Otherwise use the host URL from the request
                callback_events_uri = (
                    f"{config['ACS_DEV_TUNNEL']}/acs/callbacks"
                    if config["ACS_DEV_TUNNEL"]
                    else f"{host_url}/acs/callbacks"
                )
                
                # Construct full callback URL with GUID and caller ID
                # ACS will POST lifecycle events (connected, disconnected, etc.) to this URL
                callback_uri = f"{callback_events_uri}/{guid}?{query_parameters}"

                # ============================================================
                # CONSTRUCT WEBSOCKET URL
                # ============================================================
                # Parse the callback URL to extract hostname and port
                parsed_url = urlparse(callback_events_uri)
                
                # Construct WebSocket URL for bidirectional audio streaming
                # Use wss:// (WebSocket Secure) protocol
                websocket_url = urlunparse(
                    ("wss", parsed_url.netloc, "/acs/ws", "", "", "")
                )

                logger.info("callback url: %s", callback_uri)
                logger.info("websocket url: %s", websocket_url)

                # ============================================================
                # CONFIGURE MEDIA STREAMING OPTIONS
                # ============================================================
                # Set up bidirectional audio streaming with PCM format
                # This allows both receiving caller audio and sending AI audio
                media_streaming_options = MediaStreamingOptions(
                    transport_url=websocket_url,
                    transport_type=StreamingTransportType.WEBSOCKET,  # Use WebSocket for real-time streaming
                    content_type=MediaStreamingContentType.AUDIO,  # Stream audio only
                    audio_channel_type=MediaStreamingAudioChannelType.MIXED,  # Mixed audio from all participants
                    start_media_streaming=True,  # Start streaming immediately when call connects
                    enable_bidirectional=True,  # Allow both incoming and outgoing audio
                    audio_format=AudioFormat.PCM24_K_MONO,  # 24kHz PCM mono audio
                )

                # ============================================================
                # ANSWER THE CALL
                # ============================================================
                # Answer the incoming call with configured media streaming
                # ACS will establish WebSocket connection and start streaming audio
                result = await self.acs_client.answer_call(
                    incoming_call_context=incoming_call_context,
                    operation_context="incomingCall",  # Context for tracking this operation
                    callback_url=callback_uri,  # Where ACS will send lifecycle events
                    media_streaming=media_streaming_options,  # Audio streaming configuration
                )

                # Log successful call answer with connection ID
                logger.info(
                    "Answered call for connection id: %s", result.call_connection_id
                )
                return Response(status=200)

        # Return error if no valid events were processed
        return Response(status=400)

    async def process_callback_events(self, context_id: str, raw_events: list, config):
        """
        Process ACS callback events for call lifecycle monitoring.
        
        This method handles various call lifecycle events sent by ACS:
        - CallConnected: Call successfully established
        - MediaStreamingStarted: Audio streaming has begun
        - MediaStreamingStopped: Audio streaming has stopped
        - MediaStreamingFailed: Audio streaming encountered an error
        - CallDisconnected: Call has ended
        
        These events are sent by ACS to the callback URL configured in answer_call().
        They provide visibility into the call state and media streaming status.
        
        Args:
            context_id (str): Unique identifier for this call context (GUID)
            raw_events (list): List of ACS event dictionaries
            config (dict): Configuration dictionary (not currently used)
            
        Returns:
            Response: 200 OK after processing all events
            
        Event Flow:
            IncomingCall → CallConnected → MediaStreamingStarted → 
            [Call in progress] → MediaStreamingStopped → CallDisconnected
        """
        # Process each callback event in the batch
        for event in raw_events:
            # Extract common event data
            event_data = event["data"]
            call_connection_id = event_data["callConnectionId"]

            # Log event details for monitoring and debugging
            logger.info(
                "Received Event:-> %s, Correlation Id:-> %s, CallConnectionId:-> %s",
                event["type"],
                event_data["correlationId"],
                call_connection_id,
            )

            # ============================================================
            # CALL CONNECTED EVENT
            # ============================================================
            # Triggered when the call is successfully established
            # Use this to verify media streaming subscription details
            if event["type"] == "Microsoft.Communication.CallConnected":
                # Retrieve call properties to check media streaming configuration
                properties = await self.acs_client.get_call_connection(
                    call_connection_id
                ).get_call_properties()

                # Log media streaming subscription details
                logger.info(
                    "MediaStreamingSubscription:--> %s",
                    properties.media_streaming_subscription,
                )
                logger.info(
                    "Received CallConnected event for connection id: %s",
                    call_connection_id,
                )
                logger.info("CORRELATION ID:--> %s", event_data["correlationId"])
                logger.info("CALL CONNECTION ID:--> %s", call_connection_id)

            # ============================================================
            # MEDIA STREAMING STARTED EVENT
            # ============================================================
            # Triggered when audio streaming begins
            # Indicates bidirectional audio stream is ready
            elif event["type"] == "Microsoft.Communication.MediaStreamingStarted":
                update = event_data["mediaStreamingUpdate"]
                # Log streaming configuration and status
                logger.info(
                    "Media streaming content type:--> %s", update["contentType"]
                )
                logger.info(
                    "Media streaming status:--> %s", update["mediaStreamingStatus"]
                )
                logger.info(
                    "Media streaming status details:--> %s",
                    update["mediaStreamingStatusDetails"],
                )

            # ============================================================
            # MEDIA STREAMING STOPPED EVENT
            # ============================================================
            # Triggered when audio streaming stops (normal or abnormal)
            # May occur before call disconnection
            elif event["type"] == "Microsoft.Communication.MediaStreamingStopped":
                update = event_data["mediaStreamingUpdate"]
                # Log why streaming stopped and final status
                logger.info(
                    "Media streaming content type:--> %s", update["contentType"]
                )
                logger.info(
                    "Media streaming status:--> %s", update["mediaStreamingStatus"]
                )
                logger.info(
                    "Media streaming status details:--> %s",
                    update["mediaStreamingStatusDetails"],
                )

            # ============================================================
            # MEDIA STREAMING FAILED EVENT
            # ============================================================
            # Triggered when audio streaming encounters an error
            # Contains error codes and messages for troubleshooting
            elif event["type"] == "Microsoft.Communication.MediaStreamingFailed":
                result_info = event_data["resultInformation"]
                # Log error details for debugging
                logger.info(
                    "Code:-> %s, Subcode:-> %s",
                    result_info["code"],
                    result_info["subCode"],
                )
                logger.info("Message:-> %s", result_info["message"])

            # ============================================================
            # CALL DISCONNECTED EVENT
            # ============================================================
            # Triggered when the call ends (caller hung up or system terminated)
            # Final event in the call lifecycle
            elif event["type"] == "Microsoft.Communication.CallDisconnected":
                logger.info(
                    "CallDisconnected event received for: %s", call_connection_id
                )

        # Return success after processing all events
        return Response(status=200)
