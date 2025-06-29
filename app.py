from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
from google.cloud import texttospeech
from google.cloud import speech_v1 as speech
from google.cloud import dialogflowcx_v3beta1 as dialogflowcx
from google.api_core.client_options import ClientOptions
from google.oauth2 import service_account
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect
from functools import wraps
from dotenv import load_dotenv
import time
import base64
import os
import uuid
import json
import requests
from requests.auth import HTTPBasicAuth

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-healthcare-secret-key-2024')
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

USERS = { "humadmin12@3": "hummem123@3" }
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
DIALOGFLOW_CX_CONNECTOR_NAME = os.getenv("DIALOGFLOW_CX_CONNECTOR_NAME", "HRA")
PROJECT_ID = os.getenv("PROJECT_ID")
AGENT_ID = os.getenv("AGENT_ID")
LOCATION_ID = os.getenv("LOCATION_ID")
LANGUAGE_CODE = os.getenv("LANGUAGE_CODE", "en-US")
BASE_URL = os.getenv("BASE_URL", "https://your-domain.com")
SUMMARY_AGENT_ID = os.getenv("SUMMARY_AGENT_ID")  # Your HealthSummarization agent ID

tts_client = texttospeech.TextToSpeechClient.from_service_account_json(os.getenv("GCP_KEY_PATH"))
speech_client = speech.SpeechClient.from_service_account_json(os.getenv("GCP_KEY_PATH"))
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

credentials = service_account.Credentials.from_service_account_file(os.getenv("GCP_KEY_PATH"))
client_options = ClientOptions(api_endpoint=f"{LOCATION_ID}-dialogflow.googleapis.com:443")
dialogflow_client = dialogflowcx.SessionsClient( credentials=credentials, client_options=client_options)

# Separate client for global region summarization agent
global_client_options = ClientOptions(api_endpoint="dialogflow.googleapis.com:443")
global_dialogflow_client = dialogflowcx.SessionsClient(credentials=credentials, client_options=global_client_options)

conversations = {}
sent_user_messages = {} # Track sent messages to prevent duplicates (per session)
sent_agent_messages = {}

def load_members():
    try:
        with open('members.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        return []

members_data = load_members()

class ConversationSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.dialogflow_session_id = str(uuid.uuid4())
        self.transcript = []
        self.is_active = False
        self.agent_path = f"projects/{PROJECT_ID}/locations/{LOCATION_ID}/agents/{AGENT_ID}"
        self.session_path = f"{self.agent_path}/sessions/{self.dialogflow_session_id}"
        self.audio_count = 0
        self.selected_member = None
        self.first_message_sent = False
        self.call_sid = None
        self.call_mode = "web"  # "web" or "phone"
        self.recording_url = None
        self.recording_duration = None
        # Health Summarization agent session
        self.summary_session_id = str(uuid.uuid4())
        self.summary_agent_path = f"projects/{PROJECT_ID}/locations/global/agents/{SUMMARY_AGENT_ID}"
        self.summary_session_path = f"{self.summary_agent_path}/sessions/{self.summary_session_id}"
        self.exchange_count = 0

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def format_transcript(transcript_data):
    text_content = ""
    for entry in transcript_data:
        text_content += f"Question: {entry['question']}\n"
        text_content += f"Answer: {entry['answer']}\n"
        if "feedback" in entry:
            text_content += f"Feedback: {entry['feedback']}\n"
        text_content += "\n"
    return text_content

def text_to_speech(text):
    try:
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
            name="en-US-Chirp3-HD-Sulafat"
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.1,
            pitch=0.0
        )
        response = tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        return response.audio_content
    except Exception as e:
        print(f"Error in text-to-speech: {e}")
        return None

def speech_to_text(audio_content, encoding="WEBM_OPUS"):
    try:
        if len(audio_content) < 100:
            return None, 0
            
        audio = speech.RecognitionAudio(content=audio_content)
        encoding_map = {
            "WEBM_OPUS": speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            "LINEAR16": speech.RecognitionConfig.AudioEncoding.LINEAR16,
            "WAV": speech.RecognitionConfig.AudioEncoding.LINEAR16,
            "FLAC": speech.RecognitionConfig.AudioEncoding.FLAC,
            "OGG_OPUS": speech.RecognitionConfig.AudioEncoding.OGG_OPUS
        }
        
        selected_encoding = encoding_map.get(encoding, speech.RecognitionConfig.AudioEncoding.WEBM_OPUS)
        
        config = speech.RecognitionConfig(
            encoding=selected_encoding,
            sample_rate_hertz=48000,  # Common web audio sample rate
            language_code='en-US',
            enable_automatic_punctuation=True,
            enable_word_confidence=True,
            model='latest_short',
            use_enhanced=True,
            enable_word_time_offsets=False,
            max_alternatives=1
        )
        
        response = speech_client.recognize(config=config, audio=audio)
        if response.results:
            best_alternative = response.results[0].alternatives[0]
            transcript = best_alternative.transcript.strip()
            confidence = best_alternative.confidence
            
            if confidence > 0.3:
                return transcript, confidence
            else:
                return None, 0
        else:
            return None, 0
            
    except Exception as e:
        if encoding == "WEBM_OPUS": # Fallback to LINEAR16 if WEBM_OPUS fails
            return speech_to_text(audio_content, "LINEAR16")
        return None, 0

def get_dialogflow(text, session_path, member_params=None):
    try:
        text_input = dialogflowcx.TextInput(text=text)
        query_input = dialogflowcx.QueryInput(text=text_input, language_code=LANGUAGE_CODE)
        request = dialogflowcx.DetectIntentRequest(
            session=session_path,
            query_input=query_input,
        )
        
        if member_params:
            request.query_params = dialogflowcx.QueryParameters(
                parameters={
                    'member_id': member_params.get('member_id', ''),
                    'first_name': member_params.get('first_name', ''),
                    'last_name': member_params.get('last_name', ''),
                    'DOB': member_params.get('DOB', ''),
                    'email': member_params.get('email', ''),
                    'last4ssn': member_params.get('last4ssn', '')
                }
            )
        
        response = dialogflow_client.detect_intent(request=request)
        
        response_texts = []
        for msg in response.query_result.response_messages:
            if msg.text and msg.text.text:
                response_texts.extend(msg.text.text)
        
        if response_texts:
            return " ".join(response_texts), response.query_result
        else:
            return None, None
            
    except Exception as e:
        return None, None

def format_transcript_for_summary(transcript_data):
    """Format transcript data for the summarization agent"""
    formatted_text = ""
    for entry in transcript_data:
        if entry.get('question'):
            formatted_text += f"Customer: {entry['question']}\n"
        if entry.get('answer'):
            formatted_text += f"Agent: {entry['answer']}\n"
    return formatted_text.strip()

def call_summary_agent(session_path, query_text, transcript_text=None):
    """Call the HealthSummarization agent"""
    try:
        # Prepare the query input
        text_input = dialogflowcx.TextInput(text=query_text)
        query_input = dialogflowcx.QueryInput(text=text_input, language_code=LANGUAGE_CODE)
        
        # Create request with session parameters if transcript provided
        request = dialogflowcx.DetectIntentRequest(
            session=session_path,
            query_input=query_input,
        )
        
        # Add transcript as session parameter if provided
        if transcript_text:
            request.query_params = dialogflowcx.QueryParameters(
                parameters={'transcript': transcript_text}
            )
        
        # Use global client for summarization agent (since it's in global region)
        response = global_dialogflow_client.detect_intent(request=request)
        
        # Extract response text
        response_texts = []
        for msg in response.query_result.response_messages:
            if msg.text and msg.text.text:
                response_texts.extend(msg.text.text)
        
        if response_texts:
            return " ".join(response_texts)
        else:
            return "No summary available"
            
    except Exception as e:
        print(f"Error calling summary agent: {e}")
        return f"Error generating summary: {str(e)}"

def generate_auto_summary(session_id):
    """Generate automatic summary every few exchanges"""
    try:
        if session_id not in conversations:
            return
            
        conv = conversations[session_id]
        
        # Only generate summary if we have content and it's been a few exchanges
        if len(conv.transcript) < 2:
            return
            
        # Format transcript for summarization
        transcript_text = format_transcript_for_summary(conv.transcript)
        
        if not transcript_text.strip():
            return
            
        print(f"Generating auto-summary for session {session_id}")
        print(f"Transcript length: {len(transcript_text)} characters")
        
        # Call summarization agent
        summary = call_summary_agent(
            conv.summary_session_path, 
            "Summarize the conversation",
            transcript_text
        )
        
        print(f"Generated summary: {summary}")
        
        # Emit summary to frontend
        socketio.emit('agent_assist_summary', {
            'summary': summary,
            'timestamp': time.time(),
            'type': 'auto'
        })
        
    except Exception as e:
        print(f"Error generating auto summary: {e}")

def handle_manual_query(session_id, query):
    """Handle manual query from care manager"""
    try:
        if session_id not in conversations:
            return "No active conversation found"
            
        conv = conversations[session_id]
        
        # Format transcript for query
        transcript_text = format_transcript_for_summary(conv.transcript)
        
        if not transcript_text.strip():
            return "No conversation content available for analysis"
        
        print(f"Processing manual query for session {session_id}: {query}")
        
        # Call summarization agent with the query
        response = call_summary_agent(
            conv.summary_session_path,
            query,
            transcript_text
        )
        
        print(f"Manual query response: {response}")
        return response
        
    except Exception as e:
        print(f"Error handling manual query: {e}")
        return f"Error processing query: {str(e)}"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if username in USERS and USERS[username] == password:
            session['logged_in'] = True
            session['username'] = username
            session.permanent = True
            flash(f'Welcome, {username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password. Please try again.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    session_id = request.sid
    if session_id not in conversations:
        conversations[session_id] = ConversationSession(session_id)
    emit('connection_established', {'status': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    if session_id in conversations:
        conversations[session_id].is_active = False

@socketio.on('start_conversation')
def handle_start_conversation():
    session_id = request.sid
    
    if session_id in conversations:
        conv = conversations[session_id]
        conv.is_active = True
        conv.transcript = []
        conv.audio_count = 0
        conv.first_message_sent = False  # Reset first message flag
        conv.call_mode = "web"  # Set to web mode for microphone conversation
        
        emit('conversation_started', {
            'session_id': session_id,
            'dialogflow_session_id': conv.dialogflow_session_id,
            'timestamp': time.time(),
            'message': 'Conversation started. Please speak to begin.'
        })
        
    else:
        emit('error', {'message': 'Session not found. Please refresh the page.'})

@socketio.on('stop_conversation')
def handle_stop_conversation():
    session_id = request.sid
    
    if session_id in conversations:
        conv = conversations[session_id]
        conv.is_active = False
        
        if conv.transcript:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"transcript_{timestamp}.txt"
            
            try:
                with open(filename, 'w') as f:
                    f.write(format_transcript(conv.transcript))
                
                emit('transcript_saved', {'filename': filename})
            except Exception as e:
                print(f"Error saving transcript: {e}")
        
        emit('conversation_ended', {'session_id': session_id})

@socketio.on('audio_data')
def handle_audio_data(data):
    session_id = request.sid
    
    if session_id not in conversations:
        emit('error', {'message': 'Session not found'})
        return
    
    conv = conversations[session_id]
    if not conv.is_active:
        return
    
    try:
        conv.audio_count += 1
        emit('processing_audio', {'status': 'Processing your speech...'})
        audio_content = base64.b64decode(data['audio'])
        encoding = data.get('encoding', 'WEBM_OPUS')
        transcript, confidence = speech_to_text(audio_content, encoding)
        
        if transcript and transcript.strip():
            emit('transcription_result', {
                'text': transcript,
                'confidence': confidence
            })
            
            member_params = None # Determine if we need to send member parameters (first message only)
            if not conv.first_message_sent and conv.selected_member:
                member_params = conv.selected_member
                conv.first_message_sent = True
            
            response_text, query_result = get_dialogflow(transcript, conv.session_path, member_params)
            
            if response_text:
                
                tts_audio = text_to_speech(response_text)
                
                if tts_audio:
                    conv.transcript.append({
                        "question": transcript,
                        "answer": response_text
                    })
                    
                    emit('agent_response', {
                        'text': response_text,
                        'audio': base64.b64encode(tts_audio).decode(),
                        'timestamp': time.time()
                    })
                    
                    emit('transcript_updated', {'transcript': conv.transcript})
                    
                    # Increment exchange count and generate auto-summary every 2-3 exchanges
                    conv.exchange_count += 1
                    if conv.exchange_count % 2 == 0:  # Every 2 exchanges
                        generate_auto_summary(session_id)
                    
                    try:
                        if query_result and hasattr(query_result, 'intent') and query_result.intent:
                            if hasattr(query_result.intent, 'end_conversation') and query_result.intent.end_conversation:
                                conv.is_active = False
                                emit('conversation_should_end', {'reason': 'intent_end_conversation'})
                    except Exception as intent_error:
                        print(f"Error checking intent end_conversation: {intent_error}")
                        
                else:
                    emit('error', {'message': 'Failed to generate speech response'})
            else:
                emit('error', {'message': 'Failed to get response from Dialogflow'})
        else:
            emit('transcription_result', {
                'text': '',
                'confidence': 0,
                'message': 'No speech detected. Please try speaking again.'
            })
            
    except Exception as e:
        import traceback
        print(f"Full error traceback: {traceback.format_exc()}")
        emit('error', {'message': f'Error processing audio: {str(e)}'})

@socketio.on('get_transcript')
def handle_get_transcript():
    session_id = request.sid
    if session_id in conversations:
        conv = conversations[session_id]
        emit('current_transcript', {'transcript': conv.transcript})
    else:
        emit('error', {'message': 'No active conversation session'})

@socketio.on('select_member')
def handle_select_member(data):
    session_id = request.sid
    member_id = data.get('member_id')
    
    if session_id in conversations:
        conv = conversations[session_id]
        selected_member = None
        for member in members_data:
            if member['member_id'] == member_id:
                selected_member = member
                break
        
        if selected_member:
            conv.selected_member = selected_member
            emit('member_selected', {
                'member': selected_member,
                'message': f'Selected member: {selected_member["first_name"]} {selected_member["last_name"]}'
            })
        else:
            emit('error', {'message': 'Member not found'})
    else:
        emit('error', {'message': 'Session not found. Please refresh the page.'})

@socketio.on('agent_assist_query')
def handle_agent_assist_query(data):
    """Handle manual queries from care manager"""
    session_id = request.sid
    query = data.get('query', '').strip()
    
    if not query:
        emit('agent_assist_response', {
            'query': query,
            'response': 'Please enter a question to analyze the conversation.',
            'timestamp': time.time(),
            'type': 'manual'
        })
        return
    
    try:
        response = handle_manual_query(session_id, query)
        
        emit('agent_assist_response', {
            'query': query,
            'response': response,
            'timestamp': time.time(),
            'type': 'manual'
        })
        
    except Exception as e:
        print(f"Error handling agent assist query: {e}")
        emit('agent_assist_response', {
            'query': query,
            'response': f'Error processing query: {str(e)}',
            'timestamp': time.time(),
            'type': 'manual'
        })

@app.route('/dialogflow-webhook', methods=['POST'])
def dialogflow_webhook():
    try:
        webhook_request = request.get_json()
        if not webhook_request:
            return jsonify({'fulfillmentResponse': {'messages': []}})
        
        current_time = time.time()
        session_info = webhook_request.get('sessionInfo', {})
        session_id = session_info.get('session', '')
        parameters = session_info.get('parameters', {})
        user_query = ""
        
        # Find matching conversation session
        matching_conv = None
        matching_socket_session = None
        
        # Extract just the session ID from the full session path
        session_id_only = session_id.split('/')[-1] if '/' in session_id else session_id
        
        for socket_session_id, conv in conversations.items():
            conv_session_id = conv.dialogflow_session_id
            # Try multiple matching strategies
            if (conv_session_id == session_id_only or 
                conv.session_path.endswith(session_id) or
                conv.session_path.endswith(session_id_only)):
                matching_conv = conv
                matching_socket_session = socket_session_id
                break
        
        if 'transcript' in webhook_request:
            user_query = webhook_request['transcript'].strip()
        elif 'text' in webhook_request:
            user_query = webhook_request['text'].strip()
        elif 'dtmfDigits' in webhook_request:
            user_query = webhook_request['dtmfDigits'].strip()
        
        agent_response = ""
        messages = webhook_request.get('messages', [])
        agent_responses = []
        for message in messages:
            if 'text' in message:
                text_obj = message['text']
                if 'text' in text_obj:
                    text_variations = text_obj['text']
                    if isinstance(text_variations, list) and text_variations:
                        agent_responses.append(text_variations[0])
                    elif isinstance(text_variations, str):
                        agent_responses.append(text_variations)
        
        if agent_responses:
            agent_response = ' '.join(agent_responses).strip()
        
        fulfillment_info = webhook_request.get('fulfillmentInfo', {})
        tag = fulfillment_info.get('tag', '')
        
        intent_info = webhook_request.get('intentInfo', {})
        intent_name = intent_info.get('displayName', 'Unknown Intent')
        
        page_info = webhook_request.get('pageInfo', {})
        page_name = page_info.get('displayName', 'Unknown Page')
        
        phone_conversation_session = None
        
        # First try to find exact session match using the matching_conv we found earlier
        if matching_conv and matching_socket_session:
            phone_conversation_session = matching_socket_session
        else:
            # Fallback: try to find by member_id for outbound calls
            # PRIORITY: Find most recent outbound session over inbound sessions
            member_id = parameters.get('member_id')
            if member_id:
                outbound_candidates = []
                inbound_candidates = []
                
                for conv_session_id, conv in conversations.items():
                    if (conv.call_mode == "phone" and conv.is_active and 
                        conv.selected_member and conv.selected_member.get('member_id') == member_id):
                        
                        # Check if this is an outbound session (has call_sid from Twilio)
                        if hasattr(conv, 'call_sid') and conv.call_sid:
                            # This is an outbound session - from Twilio
                            outbound_candidates.append(conv_session_id)
                        else:
                            # This is an inbound session - no call_sid
                            inbound_candidates.append(conv_session_id)
                
                # Choose the most appropriate session
                if outbound_candidates:
                    # For outbound calls, use the latest outbound session
                    phone_conversation_session = outbound_candidates[-1]  # Most recent
                elif inbound_candidates:
                    # For inbound calls, use inbound session
                    phone_conversation_session = inbound_candidates[-1]  # Most recent
            
            # If still no match, DON'T broadcast to any session
            if not phone_conversation_session:
                return jsonify({'fulfillmentResponse': {'messages': []}})
        if phone_conversation_session:
            conv = conversations[phone_conversation_session]
            is_call_end = False
            if ('eventType' in webhook_request and 'call' in webhook_request['eventType'].lower() and 'end' in webhook_request['eventType'].lower()) or \
               ('sessionInfo' in webhook_request and 'endCallReason' in webhook_request['sessionInfo']) or \
               ('intent' in webhook_request and 'end' in str(webhook_request['intent']).lower()):
                is_call_end = True
            
            if user_query and user_query.strip():
                # Check if we've already sent this user message
                global sent_user_messages
                if phone_conversation_session not in sent_user_messages:
                    sent_user_messages[phone_conversation_session] = set()
                
                user_msg_hash = hash(user_query.strip())
                if user_msg_hash not in sent_user_messages[phone_conversation_session]:
                    sent_user_messages[phone_conversation_session].add(user_msg_hash)
                    
                    # Add to transcript
                    conv.transcript.append({
                        "question": user_query,
                        "answer": "",  # Will be filled when agent responds
                        "timestamp": current_time
                    })
                    
                    # Broadcast user message to UI
                    socketio.emit('phone_transcription_result', {
                        'text': user_query,
                        'type': 'user',
                        'timestamp': current_time
                    }, room=phone_conversation_session)
            
            if agent_response and agent_response.strip():
                # Check if we've already sent this agent message
                global sent_agent_messages
                if phone_conversation_session not in sent_agent_messages:
                    sent_agent_messages[phone_conversation_session] = set()
                
                agent_msg_hash = hash(agent_response.strip())
                if agent_msg_hash not in sent_agent_messages[phone_conversation_session]:
                    sent_agent_messages[phone_conversation_session].add(agent_msg_hash)
                    
                    if conv.transcript and not conv.transcript[-1].get("answer"):
                        conv.transcript[-1]["answer"] = agent_response
                        conv.transcript[-1]["timestamp"] = current_time
                    else:
                        conv.transcript.append({
                            "question": "",
                            "answer": agent_response,
                            "timestamp": current_time
                        })
                    
                    socketio.emit('phone_agent_response', {
                        'text': agent_response,
                        'type': 'agent',
                        'timestamp': current_time,
                        'is_call_end': is_call_end
                    }, room=phone_conversation_session)
                    socketio.emit('conversation_update', {
                        'text': agent_response,
                        'type': 'agent',
                        'timestamp': current_time,
                        'source': 'webhook',
                        'is_call_end': is_call_end
                    }, room=phone_conversation_session)
            
            socketio.emit('transcript_updated', {
                'transcript': conv.transcript
            }, room=phone_conversation_session)
            
            # Generate auto-summary for phone conversations
            if user_query and agent_response and conv:
                conv.exchange_count += 1
                if conv.exchange_count % 2 == 0:  # Every 2 exchanges
                    generate_auto_summary(phone_conversation_session)
        
        return jsonify({
            'fulfillmentResponse': {
                'messages': []
            }
        })
        
    except Exception as e:
        print(f"Error in Dialogflow webhook: {e}")
        return jsonify({
            'fulfillmentResponse': {
                'messages': []
            }
        })

@app.route('/inbound-caller-lookup', methods=['POST'])
def inbound_caller_lookup():
    try:
        webhook_request = request.get_json()
        
        payload = webhook_request.get('payload', {})
        telephony = payload.get('telephony', {})
        caller_id = telephony.get('caller_id', '')
        
        if not caller_id:
            return jsonify({
                'fulfillmentResponse': {
                    'messages': []
                },
                'sessionInfo': {
                    'parameters': {
                        'call_type': 'inbound',
                        'caller_id': '',
                        'member_found': False
                    }
                }
            })
        
        members_data = load_members()
        matching_member = None
        for member in members_data:
            if member.get('phone') == caller_id:
                matching_member = member
                break
        
        if matching_member:
            new_session_id = str(uuid.uuid4())
            conversations[new_session_id] = ConversationSession(new_session_id)
            conversations[new_session_id].call_mode = "phone"
            conversations[new_session_id].is_active = True
            conversations[new_session_id].selected_member = matching_member
            
            session_parameters = {
                'call_type': 'inbound',
                'caller_id': caller_id,
                'member_found': True,
                'member_id': matching_member.get('member_id', ''),
                'first_name': matching_member.get('first_name', ''),
                'last_name': matching_member.get('last_name', ''),
                'DOB': matching_member.get('DOB', ''),
                'email': matching_member.get('email', ''),
                'last4ssn': matching_member.get('last4ssn', ''),
                'phone': matching_member.get('phone', ''),
                'gender': matching_member.get('gender', ''),
                'insurance_plan': matching_member.get('insurance_plan', ''),
                'member_id_number': matching_member.get('member_id_number', ''),
                'group_number': matching_member.get('group_number', ''),
                'primary_physician': matching_member.get('primary_physician', ''),
                'employer_name': matching_member.get('employer_name', ''),
                'coverage_status': matching_member.get('coverage_status', ''),
                'enrollment_date': matching_member.get('enrollment_date', ''),
                'consent_signed': str(matching_member.get('consent_signed', False))
            }
            
            return jsonify({
                'fulfillmentResponse': {
                    'messages': []
                },
                'sessionInfo': {
                    'parameters': session_parameters
                }
            })
        
        else:
            return jsonify({
                'fulfillmentResponse': {
                    'messages': []
                },
                'sessionInfo': {
                    'parameters': {
                        'call_type': 'inbound',
                        'caller_id': caller_id,
                        'member_found': False
                    }
                }
            })
    
    except Exception as e:
        return jsonify({
            'fulfillmentResponse': {
                'messages': []
            },
            'sessionInfo': {
                'parameters': {
                    'call_type': 'inbound',
                    'error': 'lookup_failed'
                }
            }
        })

@app.route('/api/members')
@login_required
def get_members():
    return jsonify(members_data)

@app.route('/api/recording/<session_id>')
@login_required
def get_recording(session_id):
    """
    Get recording information for a specific session
    """
    if session_id in conversations:
        conv = conversations[session_id]
        if hasattr(conv, 'recording_url') and conv.recording_url:
            return jsonify({
                'call_sid': conv.call_sid,
                'recording_url': conv.recording_url,
                'recording_duration': conv.recording_duration,
                'member_name': f"{conv.selected_member['first_name']} {conv.selected_member['last_name']}" if conv.selected_member else "Unknown"
            })
        else:
            return jsonify({'error': 'No recording available for this session'}), 404
    else:
        return jsonify({'error': 'Session not found'}), 404

@app.route('/api/download-recording/<recording_sid>')
@login_required
def download_recording(recording_sid):
    """
    Download recording file by proxying the Twilio URL with authentication
    """
    try:
        # Construct the Twilio recording URL
        recording_url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Recordings/{recording_sid}.mp3"
        
        # Make authenticated request to Twilio
        response = requests.get(
            recording_url,
            auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            stream=True
        )
        
        if response.status_code == 200:
            # Stream the audio file back to the client
            def generate():
                for chunk in response.iter_content(chunk_size=8192):
                    yield chunk
            
            return app.response_class(
                generate(),
                mimetype='audio/mpeg',
                headers={
                    'Content-Disposition': f'inline; filename="recording_{recording_sid}.mp3"',
                    'Content-Type': 'audio/mpeg'
                }
            )
        else:
            return jsonify({'error': 'Recording not found'}), 404
            
    except Exception as e:
        print(f"Error downloading recording: {e}")
        return jsonify({'error': 'Failed to download recording'}), 500

@app.route('/recording-webhook', methods=['POST'])
def handle_recording_webhook():
    """
    Webhook called by Twilio when call recording is complete.
    This provides the recording URL and metadata.
    """
    try:
        # Get recording data from Twilio webhook
        call_sid = request.form.get('CallSid')
        recording_url = request.form.get('RecordingUrl')
        recording_duration = request.form.get('RecordingDuration')
        recording_sid = request.form.get('RecordingSid')
        
        print(f"Recording webhook received for call {call_sid}")
        print(f"Recording URL: {recording_url}")
        print(f"Duration: {recording_duration} seconds")
        
        if not call_sid or not recording_url:
            print("Missing required recording data")
            return '', 400
        
        # Find the conversation session with this call_sid
        matching_session = None
        for session_id, conv in conversations.items():
            if hasattr(conv, 'call_sid') and conv.call_sid == call_sid:
                matching_session = session_id
                break
        
        if matching_session:
            conv = conversations[matching_session]
            conv.recording_url = recording_url
            conv.recording_duration = recording_duration
            
            # Notify the UI that recording is available
            socketio.emit('recording_available', {
                'call_sid': call_sid,
                'recording_url': recording_url,
                'recording_duration': recording_duration,
                'recording_sid': recording_sid,
                'member_name': f"{conv.selected_member['first_name']} {conv.selected_member['last_name']}" if conv.selected_member else "Unknown",
                'timestamp': time.time()
            }, room=matching_session)
            
            print(f"Recording info saved for session {matching_session}")
        else:
            print(f"No matching conversation session found for call {call_sid}")
        
        return '', 200
        
    except Exception as e:
        print(f"Error in recording webhook: {e}")
        return '', 500

def get_webhook_base_url():
    """
    Get the base URL for webhooks - uses Cloud Run URL in production, ngrok for local development
    """
    # Check if we're in production (Cloud Run sets this environment variable)
    webhook_base_url = os.getenv('WEBHOOK_BASE_URL')
    if webhook_base_url:
        print(f"Using production webhook URL: {webhook_base_url}")
        return webhook_base_url
    
    # Fall back to ngrok for local development
    try:
        # ngrok exposes tunnels info at localhost:4040
        response = requests.get('http://localhost:4040/api/tunnels')
        if response.status_code == 200:
            tunnels = response.json()['tunnels']
            for tunnel in tunnels:
                if tunnel['proto'] == 'https':
                    ngrok_url = tunnel['public_url']
                    print(f"Using local ngrok URL: {ngrok_url}")
                    return ngrok_url
        print("No ngrok tunnel found")
        return None
    except Exception as e:
        print(f"Could not get ngrok URL: {e}")
        return None

def make_outbound_call(member_data):
    if not twilio_client:
        return None, "Twilio not configured"
    if not member_data.get('phone'):
        return None, "No phone number for member"
    
    try:
        response = VoiceResponse()
        connect = Connect()
        virtual_agent = connect.virtual_agent(connector_name=DIALOGFLOW_CX_CONNECTOR_NAME)
        virtual_agent.parameter(name='member_id', value=member_data.get('member_id', ''))
        virtual_agent.parameter(name='first_name', value=member_data.get('first_name', ''))
        virtual_agent.parameter(name='last_name', value=member_data.get('last_name', ''))
        virtual_agent.parameter(name='DOB', value=member_data.get('DOB', ''))
        virtual_agent.parameter(name='email', value=member_data.get('email', ''))
        virtual_agent.parameter(name='last4ssn', value=member_data.get('last4ssn', ''))
        virtual_agent.parameter(name='phone', value=member_data.get('phone', ''))
        virtual_agent.parameter(name='gender', value=member_data.get('gender', ''))
        virtual_agent.parameter(name='insurance_plan', value=member_data.get('insurance_plan', ''))
        virtual_agent.parameter(name='member_id_number', value=member_data.get('member_id_number', ''))
        virtual_agent.parameter(name='group_number', value=member_data.get('group_number', ''))
        virtual_agent.parameter(name='primary_physician', value=member_data.get('primary_physician', ''))
        virtual_agent.parameter(name='employer_name', value=member_data.get('employer_name', ''))
        virtual_agent.parameter(name='coverage_status', value=member_data.get('coverage_status', ''))
        virtual_agent.parameter(name='enrollment_date', value=member_data.get('enrollment_date', ''))
        virtual_agent.parameter(name='consent_signed', value=str(member_data.get('consent_signed', False)))
        response.append(connect)
        twiml_content = str(response)
        
        # Get the base URL for the recording webhook
        base_url = get_webhook_base_url()
        if not base_url:
            # Fallback to BASE_URL environment variable if neither Cloud Run nor ngrok is available
            base_url = os.getenv('BASE_URL', 'https://your-domain.com')
            print(f"Using fallback BASE_URL: {base_url}")
        
        recording_callback_url = f"{base_url}/recording-webhook"
        
        print(f"Using webhook URL: {recording_callback_url}")  # Debug log
        
        call = twilio_client.calls.create(
            to=member_data['phone'],
            from_=TWILIO_PHONE_NUMBER,
            twiml=twiml_content,
            record=True,  # Enable call recording
            recording_status_callback=recording_callback_url,
            recording_status_callback_method='POST'
        )
        return call.sid, None
        
    except Exception as e:
        print(f"Error making outbound call: {e}")
        return None, str(e)

@socketio.on('initiate_call')
def handle_initiate_call():
    session_id = request.sid
    
    if session_id not in conversations:
        emit('error', {'message': 'Session not found. Please refresh the page.'})
        return
    
    conv = conversations[session_id]
    
    if not conv.selected_member:
        emit('error', {'message': 'Please select a member before initiating a call.'})
        return
    
    if not conv.selected_member.get('phone'):
        emit('error', {'message': 'Selected member has no phone number.'})
        return
    
    call_sid, error = make_outbound_call(conv.selected_member)
    
    if error:
        emit('error', {'message': f'Failed to initiate call: {error}'})
        return
    
    conv.call_sid = call_sid
    conv.call_mode = "phone"
    conv.is_active = True
    conv.transcript = []
    conv.audio_count = 0
    conv.first_message_sent = False
    
    global sent_user_messages, sent_agent_messages
    if session_id in sent_user_messages:
        del sent_user_messages[session_id]
    if session_id in sent_agent_messages:
        del sent_agent_messages[session_id]
    
    emit('call_initiated', {
        'call_sid': call_sid,
        'member_phone': conv.selected_member['phone'],
        'member_name': f"{conv.selected_member['first_name']} {conv.selected_member['last_name']}",
        'message': f'Calling {conv.selected_member["first_name"]} at {conv.selected_member["phone"]}...'
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8082))
    print(f"Starting server on port: {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False) 