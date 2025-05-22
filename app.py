from flask import Flask, render_template, jsonify, Response
import time
import threading
from google.cloud import texttospeech
from google.cloud import speech_v1 as speech
from google.cloud import dialogflowcx_v3beta1 as dialogflowcx
import pygame
import os
import pyaudio
import wave
import tempfile
import uuid
import io
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=1024)

tts_client = texttospeech.TextToSpeechClient.from_service_account_json(os.getenv("GCP_KEY_PATH"))
speech_client = speech.SpeechClient.from_service_account_json(os.getenv("GCP_KEY_PATH"))


PROJECT_ID = os.getenv("PROJECT_ID")
AGENT_ID = os.getenv("AGENT_ID")
LOCATION_ID = os.getenv("LOCATION_ID")
LANGUAGE_CODE = os.getenv("LANGUAGE_CODE")

api_endpoint = f"{LOCATION_ID}-dialogflow.googleapis.com:443"
client_options = {"api_endpoint": api_endpoint}
dialogflow_client = dialogflowcx.SessionsClient(client_options=client_options)

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
MAX_RECORDING_SECONDS = 30
SILENCE_THRESHOLD = 300
SILENCE_SECONDS = 0.5
MAX_SILENCE_CHUNKS = int(RATE / CHUNK * SILENCE_SECONDS)

conversation_active = False
transcript = []
current_session_id = None
current_question = None
current_answer = None
is_listening = False
is_processing = False
recording_thread = None
stop_recording = threading.Event()

def format_transcript_as_text(transcript_data):
    text_content = ""
    for entry in transcript_data:
        text_content += f"Question: {entry['question']}\n"
        text_content += f"Answer: {entry['answer']}\n"
        if "feedback" in entry:
            text_content += f"Feedback: {entry['feedback']}\n"
        text_content += "\n"
    return text_content

def speak_text(text):
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=1024)
        
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
            name="en-US-Chirp3-HD-Sulafat"
        )
        
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.1,  # Slightly faster speaking rate
            pitch=0.0
        )
        
        response = tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        pygame.mixer.music.load(io.BytesIO(response.audio_content))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(30)  # Increased from 10 to 30
            
    except Exception as e:
        print(f"Error in text-to-speech: {e}")
    finally:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()

def record_audio():
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    frames = []
    silent_chunks = 0
    started = False
    max_audio_level = 0
    
    try:
        while not stop_recording.is_set():
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                
                audio_data = wave.struct.unpack("%dh" % (len(data) / 2), data) # Calculate audio level using RMS (Root Mean Square)
                audio_level = int(sum(abs(x) for x in audio_data) / len(audio_data))
                max_audio_level = max(max_audio_level, audio_level)
                
                if audio_level > SILENCE_THRESHOLD and not started:
                    print(f"Speech detected! Audio level: {audio_level}")
                    started = True
                    silent_chunks = 0
                elif started:
                    if audio_level <= SILENCE_THRESHOLD:
                        silent_chunks += 1
                        if silent_chunks % 10 == 0:
                            print(f"Silence detected... {silent_chunks}/{MAX_SILENCE_CHUNKS} chunks")
                    else:
                        silent_chunks = 0
                    if silent_chunks >= MAX_SILENCE_CHUNKS:
                        print("Silence threshold reached, stopping recording")
                        break
            except Exception as e:
                print(f"Error reading audio data: {e}")
                break
        
        if not started:
            print("No speech detected during recording")
            return None
            
        if len(frames) < 10:  # If we recorded less than 10 chunks, it's probably not valid speech
            print("Recording too short, probably not valid speech")
            return None
            
        return frames
        
    except Exception as e:
        return None
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

def save_audio_to_wav(frames, filename):
    wf = wave.open(filename, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(2)  # 2 bytes for paInt16
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

def transcribe_audio(audio_file):
    try:
        print(f"\n=== Starting Transcription ===")
        
        with open(audio_file, 'rb') as audio_file:
            content = audio_file.read()
        
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=RATE,
            language_code='en-US',
            enable_automatic_punctuation=True
        )
        
        response = speech_client.recognize(config=config, audio=audio)
        
        if response.results:
            transcript_text = response.results[0].alternatives[0].transcript
            confidence = response.results[0].alternatives[0].confidence
            print(f'Transcript: {transcript_text}')
            print(f'Confidence: {confidence}')
            return transcript_text
        else:
            print("No transcription results returned")
            return None
            
    except Exception as e:
        print(f"Error in transcription: {e}")
        return None

def recognize_speech():
    global is_listening, current_answer
    is_listening = True
    stop_recording.clear()
    temp_file = None
    
    try:
        print("Recording audio...")
        frames = record_audio()
        
        if not frames:
            is_listening = False
            return None
        
        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_file.close()
        save_audio_to_wav(frames, temp_file.name)
        text = transcribe_audio(temp_file.name)
        print(f"Transcription result: {text}")
        is_listening = False
        
        if text and text.strip():
            print(f"Transcription successful: {text}")
            current_answer = text
            return text
        else:
            return None
            
    except Exception as e:
        is_listening = False
        return None
    finally:
        try:
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
        except Exception as e:
            print(f"Error cleaning up temp file: {e}")

def conversation_thread():
    global conversation_active, transcript, current_session_id, current_question, current_answer, is_listening
    current_session_id = str(uuid.uuid4())
    agent_path = f"projects/{PROJECT_ID}/locations/{LOCATION_ID}/agents/{AGENT_ID}"
    session_path = f"{agent_path}/sessions/{current_session_id}"
    
    while conversation_active:
        try:
            print("\n=== Processing Dialogflow CX Interaction ===")
            
            if current_answer:
                text_input = dialogflowcx.TextInput(text=current_answer)
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
                    current_question = " ".join(response_texts)
                    print(f"Agent response: {current_question}")
                    speak_text(current_question)
                    transcript.append({
                        "question": current_question,
                        "answer": current_answer
                    })
                    current_answer = None
                    
                    # Check if the conversation should end
                    if response.query_result.intent and response.query_result.intent.end_conversation:
                        conversation_active = False
                        break
                else:
                    time.sleep(0.5)
                    continue
            is_listening = True
            print("Listening for user input...")
            response = recognize_speech()
            is_listening = False
            
            if response and response.strip():
                print(f"User said: {response}")
                current_answer = response
            else:
                print("No valid response received")
                time.sleep(0.5)
                continue
                
        except Exception as e:
            print(f"Error in conversation thread: {e}")
            is_listening = False
            time.sleep(0.5)
            continue
    conversation_active = False
    current_question = None
    current_answer = None
    is_listening = False
    if transcript:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"transcript_{timestamp}.txt"
        print(f"Saving transcript to {filename}")
        
        with open(filename, 'w') as f:
            f.write(format_transcript_as_text(transcript))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_conversation', methods=['POST'])
def start_conversation():
    global conversation_active, transcript, current_session_id, current_question, current_answer, is_listening
    
    conversation_active = True
    transcript = []
    current_session_id = None
    current_question = None
    current_answer = None
    is_listening = False
    
    thread = threading.Thread(target=conversation_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({"success": True, "message": "Conversation started"})

@app.route('/stop_conversation', methods=['POST'])
def stop_conversation():
    global conversation_active, is_listening
    
    conversation_active = False
    is_listening = False
    
    return jsonify({"success": True, "message": "Conversation stopped"})

@app.route('/get_transcript', methods=['GET'])
def get_transcript():
    global transcript
    return jsonify({"transcript": transcript})

@app.route('/download_transcript', methods=['GET'])
def download_transcript():
    global transcript
    
    if not transcript:
        return "No transcript available", 404
    
    text_content = format_transcript_as_text(transcript)
    filename = f"transcript_{time.strftime('%Y%m%d-%H%M%S')}.txt"
    response = Response(text_content, mimetype='text/plain')
    response.headers.set('Content-Disposition', f'attachment; filename={filename}')
    return response

@app.route('/conversation_status', methods=['GET'])
def conversation_status():
    global conversation_active, transcript, current_question, current_answer, is_listening
    
    status = {
        "active": conversation_active,
        "current_question": current_question,
        "current_answer": current_answer,
        "is_listening": is_listening,
        "completed": not conversation_active and len(transcript) > 0
    }
    
    return jsonify(status)

if __name__ == '__main__':
    app.run(debug=True) 