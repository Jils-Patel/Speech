from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import time
import base64
import os
import uuid
import json
import hashlib
from functools import wraps
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from google.cloud import texttospeech
from google.cloud import speech_v1 as speech
from google.cloud import dialogflowcx_v3beta1 as dialogflowcx
from google.api_core.client_options import ClientOptions
from google.oauth2 import service_account
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-healthcare-secret-key-2024')
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour session
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

# Simple user credentials (change these to your preferred username/password)
USERS = {
    "humadmin12@3": "hummem123@3"  # Only username/password that works
}

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Load members data
def load_members():
    try:
        with open('members.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading members.json: {e}")
        return []

members_data = load_members()

# Initialize Google Cloud clients
tts_client = texttospeech.TextToSpeechClient.from_service_account_json(os.getenv("GCP_KEY_PATH"))
speech_client = speech.SpeechClient.from_service_account_json(os.getenv("GCP_KEY_PATH"))

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
DIALOGFLOW_CX_CONNECTOR_NAME = os.getenv("DIALOGFLOW_CX_CONNECTOR_NAME", "HRA")

# Initialize Twilio client
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

PROJECT_ID = os.getenv("PROJECT_ID")
AGENT_ID = os.getenv("AGENT_ID")
LOCATION_ID = os.getenv("LOCATION_ID")
LANGUAGE_CODE = os.getenv("LANGUAGE_CODE", "en-US")

credentials = service_account.Credentials.from_service_account_file(os.getenv("GCP_KEY_PATH"))
api_endpoint = f"{LOCATION_ID}-dialogflow.googleapis.com:443"
client_options = ClientOptions(api_endpoint=api_endpoint)
dialogflow_client = dialogflowcx.SessionsClient(
    credentials=credentials,
    client_options=client_options
)

conversations = {}  # Store per-session conversation state

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

def format_transcript_as_text(transcript_data):
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

def transcribe_audio_content(audio_content, encoding="WEBM_OPUS"):
    try:
        print(f"Transcription attempt - encoding: {encoding}, audio size: {len(audio_content)}")
        if len(audio_content) < 100:
            return None, 0
            
        audio = speech.RecognitionAudio(content=audio_content)
        
        # Simplified encoding mapping - removed MP3 which isn't supported
        encoding_map = {
            "WEBM_OPUS": speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            "LINEAR16": speech.RecognitionConfig.AudioEncoding.LINEAR16,
            "WAV": speech.RecognitionConfig.AudioEncoding.LINEAR16,
            "FLAC": speech.RecognitionConfig.AudioEncoding.FLAC,
            "OGG_OPUS": speech.RecognitionConfig.AudioEncoding.OGG_OPUS
        }
        
        selected_encoding = encoding_map.get(encoding, speech.RecognitionConfig.AudioEncoding.WEBM_OPUS)
        print(f"Selected encoding enum: {selected_encoding}")
        
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
        print(f"Response received: {len(response.results) if response.results else 0} results")
        
        if response.results:
            best_alternative = response.results[0].alternatives[0]
            transcript = best_alternative.transcript.strip()
            confidence = best_alternative.confidence
            
            print(f"Transcription successful: '{transcript}' (confidence: {confidence:.2f})")
            
            if confidence > 0.3:
                return transcript, confidence
            else:
                print(f"Low confidence transcription rejected: {confidence:.2f}")
                return None, 0
        else:
            print("No transcription results returned")
            return None, 0
            
    except Exception as e:
        import traceback
        print(f"Transcription error: {e}")
        print(f"Full traceback: {traceback.format_exc()}")
        
        # Fallback to LINEAR16 if WEBM_OPUS fails
        if encoding == "WEBM_OPUS":
            print("Retrying with LINEAR16 encoding...")
            return transcribe_audio_content(audio_content, "LINEAR16")
        
        return None, 0

def process_with_dialogflow(text, session_path, member_params=None):
    try:
        text_input = dialogflowcx.TextInput(text=text)
        query_input = dialogflowcx.QueryInput(text=text_input, language_code=LANGUAGE_CODE)
        
        request = dialogflowcx.DetectIntentRequest(
            session=session_path,
            query_input=query_input,
        )
        
        # Add member parameters as session parameters if provided (first message only)
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
            print(f"Sending member parameters to Dialogflow: {member_params}")
        
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
        print(f"Error in Dialogflow processing: {e}")
        return None, None

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Simple login page"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Check credentials
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
    """Logout and clear session"""
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index_cloud.html')

@socketio.on('connect')
def handle_connect():
    session_id = request.sid
    print(f'Client connected: {session_id}')
    if session_id not in conversations:
        conversations[session_id] = ConversationSession(session_id)
    emit('connection_established', {'status': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    print(f'Client disconnected: {session_id}')
    if session_id in conversations:
        conversations[session_id].is_active = False

@socketio.on('start_conversation')
def handle_start_conversation():
    session_id = request.sid
    print(f'Starting conversation for session: {session_id}')
    
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
        
        print(f"Conversation ready for session {session_id}. Waiting for user input.")
    else:
        emit('error', {'message': 'Session not found. Please refresh the page.'})

@socketio.on('stop_conversation')
def handle_stop_conversation():
    session_id = request.sid
    print(f'Stopping conversation for session: {session_id}')
    
    if session_id in conversations:
        conv = conversations[session_id]
        conv.is_active = False
        
        if conv.transcript:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"transcript_{timestamp}.txt"
            
            try:
                with open(filename, 'w') as f:
                    f.write(format_transcript_as_text(conv.transcript))
                
                emit('transcript_saved', {'filename': filename})
            except Exception as e:
                print(f"Error saving transcript: {e}")
        
        emit('conversation_ended', {'session_id': session_id})

@socketio.on('audio_data')
def handle_audio_data(data):
    session_id = request.sid
    
    if session_id not in conversations:
        print(f"No session found for {session_id}, creating new one")
        conversations[session_id] = ConversationSession(session_id)
        emit('error', {'message': 'Session was reset. Please restart the conversation.'})
        return
    
    conv = conversations[session_id]
    if not conv.is_active:
        emit('error', {'message': 'Conversation not active'})
        return
    
    try:
        conv.audio_count += 1
        print(f'Received audio data for session: {session_id} (audio #{conv.audio_count})')
        emit('processing_audio', {'status': 'Processing your speech...'})
        
        # Decode audio data
        audio_content = base64.b64decode(data['audio'])
        encoding = data.get('encoding', 'WEBM_OPUS')
        
        print(f'Audio content size: {len(audio_content)} bytes, encoding: {encoding}')
        
        transcript, confidence = transcribe_audio_content(audio_content, encoding)
        
        if transcript and transcript.strip():
            print(f'Transcription: {transcript} (confidence: {confidence})')
            emit('transcription_result', {
                'text': transcript,
                'confidence': confidence
            })
            
            # Determine if we need to send member parameters (first message only)
            member_params = None
            if not conv.first_message_sent and conv.selected_member:
                member_params = conv.selected_member
                conv.first_message_sent = True
                print(f"Sending member parameters on first message: {member_params}")
            
            response_text, query_result = process_with_dialogflow(transcript, conv.session_path, member_params)
            
            if response_text:
                print(f'Dialogflow response: {response_text}')
                
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
                    
                    try:
                        if query_result and hasattr(query_result, 'intent') and query_result.intent:
                            if hasattr(query_result.intent, 'end_conversation') and query_result.intent.end_conversation:
                                print("Dialogflow indicated end of conversation")
                                conv.is_active = False
                                emit('conversation_should_end', {'reason': 'intent_end_conversation'})
                    except Exception as intent_error:
                        print(f"Error checking intent end_conversation: {intent_error}")
                        
                else:
                    emit('error', {'message': 'Failed to generate speech response'})
            else:
                emit('error', {'message': 'Failed to get response from Dialogflow'})
        else:
            print(f"No valid transcription for audio #{conv.audio_count}")
            emit('transcription_result', {
                'text': '',
                'confidence': 0,
                'message': 'No speech detected. Please try speaking again.'
            })
            
    except Exception as e:
        print(f'Error processing audio #{conv.audio_count}: {e}')
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
    
    print(f'Member selected for session {session_id}: {member_id}')
    
    if session_id in conversations:
        conv = conversations[session_id]
        
        # Find the selected member in members_data
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
            print(f"Member {selected_member['first_name']} {selected_member['last_name']} selected for session {session_id}")
        else:
            emit('error', {'message': 'Member not found'})
    else:
        emit('error', {'message': 'Session not found. Please refresh the page.'})

@app.route('/dialogflow-webhook', methods=['POST'])
def dialogflow_webhook():
    """Webhook to receive conversation events from Dialogflow CX during phone calls"""
    try:
        # Get the webhook request data
        webhook_request = request.get_json()
        
        if not webhook_request:
            return jsonify({'fulfillmentResponse': {'messages': []}})
        
        print(f"Full webhook payload: {webhook_request}")
        
        # Extract conversation information
        session_info = webhook_request.get('sessionInfo', {})
        session_id = session_info.get('session', '')
        parameters = session_info.get('parameters', {})
        
        # Extract the actual user query text - the 'transcript' field contains user speech
        query_text = ""
        agent_response = ""
        
        # Primary source: transcript field (this is where user speech appears in phone calls)
        if 'transcript' in webhook_request:
            query_text = webhook_request['transcript'].strip()
        
        # Fallback: try other possible locations for user input
        if not query_text:
            if 'text' in webhook_request:
                query_text = webhook_request['text']
            elif 'queryText' in webhook_request:
                query_text = webhook_request['queryText']
            elif 'query' in webhook_request:
                query_text = webhook_request['query']
            
            # Try to get from queryResult (this often contains the user's original input)
            if 'queryResult' in webhook_request:
                query_result = webhook_request['queryResult']
                if 'queryText' in query_result:
                    query_text = query_result['queryText']
                elif 'text' in query_result:
                    query_text = query_result['text']
            
            # Try to get from originalDetectIntentRequest
            if 'originalDetectIntentRequest' in webhook_request:
                original_request = webhook_request['originalDetectIntentRequest']
                if 'payload' in original_request:
                    payload = original_request['payload']
                    if 'query' in payload:
                        query_text = payload['query']
                    elif 'text' in payload:
                        query_text = payload['text']
            
            # Try to get from detectIntentRequest
            if 'detectIntentRequest' in webhook_request:
                detect_intent = webhook_request['detectIntentRequest']
                if 'queryInput' in detect_intent:
                    query_input = detect_intent['queryInput']
                    if 'text' in query_input:
                        text_input = query_input['text']
                        if 'text' in text_input:
                            query_text = text_input['text']
        
        # Try to get from fulfillmentInfo for user input
        fulfillment_info = webhook_request.get('fulfillmentInfo', {})
        tag = fulfillment_info.get('tag', '')
        
        # Get intent information
        intent_info = webhook_request.get('intentInfo', {})
        intent_name = intent_info.get('displayName', 'Unknown Intent')
        
        # Get page information
        page_info = webhook_request.get('pageInfo', {})
        page_name = page_info.get('displayName', 'Unknown Page')
        
        # Try to extract messages from the response
        messages = []
        if 'messages' in webhook_request:
            messages = webhook_request['messages']
        elif 'fulfillmentResponse' in webhook_request:
            fulfillment_response = webhook_request['fulfillmentResponse']
            if 'messages' in fulfillment_response:
                messages = fulfillment_response['messages']
        
        # Extract text from messages
        for message in messages:
            if 'text' in message and 'text' in message['text']:
                agent_response = ' '.join(message['text']['text'])
                break
        
        print(f"Webhook received:")
        print(f"  Session: {session_id}")
        print(f"  User Query: '{query_text}'")
        print(f"  Agent Response: '{agent_response}'")
        print(f"  Intent: {intent_name}")
        print(f"  Page: {page_name}")
        print(f"  Tag: {tag}")
        print(f"  Parameters: {parameters}")
        
        # Find the conversation session that matches this phone call
        phone_conversation_session = None
        for conv_session_id, conv in conversations.items():
            if conv.call_mode == "phone" and conv.is_active:
                # For phone calls, we'll match based on member parameters or session
                if (parameters.get('member_id') == conv.selected_member.get('member_id') if conv.selected_member else False):
                    phone_conversation_session = conv_session_id
                    break
                # Fallback: use the most recent active phone conversation
                phone_conversation_session = conv_session_id
        
        # If we found a matching session, broadcast the conversation update
        if phone_conversation_session:
            conv = conversations[phone_conversation_session]
            
            # If we have user query text, it's a user message
            if query_text and query_text.strip():
                print(f"Broadcasting user message: {query_text}")
                
                # Check if this is a duplicate (sometimes webhooks fire multiple times)
                is_duplicate = False
                if conv.transcript and conv.transcript[-1].get("question") == query_text:
                    is_duplicate = True
                
                if not is_duplicate:
                    conv.transcript.append({
                        "question": query_text,
                        "answer": ""  # Will be filled when agent responds
                    })
                    
                    # Broadcast user message to UI
                    socketio.emit('phone_transcription_result', {
                        'text': query_text,
                        'type': 'user',
                        'timestamp': time.time()
                    }, room=phone_conversation_session)
            
            # If we have agent response text, it's an agent message
            if agent_response and agent_response.strip():
                print(f"Broadcasting agent response: {agent_response}")
                
                # Check if this is a duplicate response
                is_duplicate = False
                if conv.transcript and conv.transcript[-1].get("answer") == agent_response:
                    is_duplicate = True
                
                if not is_duplicate:
                    # Update the last transcript entry or create new one
                    if conv.transcript and not conv.transcript[-1].get("answer"):
                        conv.transcript[-1]["answer"] = agent_response
                    else:
                        # New agent message without user input
                        conv.transcript.append({
                            "question": "",
                            "answer": agent_response
                        })
                    
                    # Broadcast agent response to UI
                    socketio.emit('phone_agent_response', {
                        'text': agent_response,
                        'type': 'agent',
                        'timestamp': time.time()
                    }, room=phone_conversation_session)
            
            # Update transcript
            socketio.emit('transcript_updated', {
                'transcript': conv.transcript
            }, room=phone_conversation_session)
        
        # Return empty fulfillment response to continue normal conversation flow
        return jsonify({
            'fulfillmentResponse': {
                'messages': []
            }
        })
        
    except Exception as e:
        print(f"Error in Dialogflow webhook: {e}")
        import traceback
        print(f"Full error traceback: {traceback.format_exc()}")
        
        # Return empty response to not break the conversation
        return jsonify({
            'fulfillmentResponse': {
                'messages': []
            }
        })

@app.route('/api/members')
@login_required
def get_members():
    """API endpoint to get list of members"""
    return jsonify(members_data)

def make_outbound_call(member_data):
    """Make an outbound call to the member using Twilio"""
    if not twilio_client:
        print("Twilio client not initialized - missing credentials")
        return None, "Twilio not configured"
    
    if not member_data.get('phone'):
        print("No phone number found for member")
        return None, "No phone number for member"
    
    try:
        # Create TwiML to connect to Dialogflow CX
        response = VoiceResponse()
        connect = Connect()
        
        # Add member parameters to the virtual agent connection
        virtual_agent = connect.virtual_agent(connector_name=DIALOGFLOW_CX_CONNECTOR_NAME)
        
        # Pass member parameters as session parameters to Dialogflow CX
        # These will be available as $session.params.first_name, etc.
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
        
        print(f"Making call to {member_data['phone']} from {TWILIO_PHONE_NUMBER}")
        print(f"Passing member parameters: {member_data.get('first_name', '')} {member_data.get('last_name', '')}")
        print(f"TwiML: {twiml_content}")
        
        # Make the outbound call
        call = twilio_client.calls.create(
            to=member_data['phone'],
            from_=TWILIO_PHONE_NUMBER,
            twiml=twiml_content
        )
        
        print(f"Call initiated successfully! Call SID: {call.sid}")
        return call.sid, None
        
    except Exception as e:
        print(f"Error making outbound call: {e}")
        return None, str(e)

@socketio.on('initiate_call')
def handle_initiate_call():
    session_id = request.sid
    print(f'Initiating call for session: {session_id}')
    
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
    
    # Make the outbound call
    call_sid, error = make_outbound_call(conv.selected_member)
    
    if error:
        emit('error', {'message': f'Failed to initiate call: {error}'})
        return
    
    # Update conversation session
    conv.call_sid = call_sid
    conv.call_mode = "phone"
    conv.is_active = True
    conv.transcript = []
    conv.audio_count = 0
    conv.first_message_sent = False
    
    emit('call_initiated', {
        'call_sid': call_sid,
        'member_phone': conv.selected_member['phone'],
        'member_name': f"{conv.selected_member['first_name']} {conv.selected_member['last_name']}",
        'message': f'Calling {conv.selected_member["first_name"]} at {conv.selected_member["phone"]}...'
    })
    
    print(f"Call initiated for {conv.selected_member['first_name']} {conv.selected_member['last_name']} at {conv.selected_member['phone']}")

if __name__ == '__main__':
    print("Starting health assessment server...")
    print(f"Project: {PROJECT_ID}")
    print(f"Agent: {AGENT_ID}")
    print(f"Location: {LOCATION_ID}")
    
    # Get port from environment variable (Cloud Run requirement) or default to 8080
    port = int(os.getenv('PORT', 8080))
    print(f"Starting server on port: {port}")
    
    socketio.run(app, host='0.0.0.0', port=port, debug=False) 