from flask import Flask, render_template, request
import time
import base64
import os
import uuid
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from google.cloud import texttospeech
from google.cloud import speech_v1 as speech
from google.cloud import dialogflowcx_v3beta1 as dialogflowcx
from google.api_core.client_options import ClientOptions
from google.oauth2 import service_account

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'speech_conversation_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

# Initialize Google Cloud clients
tts_client = texttospeech.TextToSpeechClient.from_service_account_json(os.getenv("GCP_KEY_PATH"))
speech_client = speech.SpeechClient.from_service_account_json(os.getenv("GCP_KEY_PATH"))

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

def process_with_dialogflow(text, session_path):
    try:
        text_input = dialogflowcx.TextInput(text=text)
        query_input = dialogflowcx.QueryInput(text=text_input, language_code=LANGUAGE_CODE)
        
        request = dialogflowcx.DetectIntentRequest(
            session=session_path,
            query_input=query_input,
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
        print(f"Error in Dialogflow processing: {e}")
        return None, None

@app.route('/')
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
            
            response_text, query_result = process_with_dialogflow(transcript, conv.session_path)
            
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

if __name__ == '__main__':
    print("Starting health assessment server...")
    print(f"Project: {PROJECT_ID}")
    print(f"Agent: {AGENT_ID}")
    print(f"Location: {LOCATION_ID}")
    socketio.run(app, host='0.0.0.0', port=8080, debug=True) 