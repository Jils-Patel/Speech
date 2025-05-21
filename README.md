# Speech Conversation App

A Flask-based web application that conducts automated interviews using speech recognition and text-to-speech capabilities.

## Features

- Real-time speech recognition
- Text-to-speech for questions
- Automated interview flow
- Transcript generation and download
- Web-based interface

## Prerequisites

- Python 3.7+
- Google Cloud account with Speech-to-Text and Text-to-Speech APIs enabled
- Google Cloud service account key (gcp_key.json)

## Installation

1. Clone the repository:
```bash
git clone <your-repository-url>
cd <repository-name>
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up Google Cloud credentials:
   - Create a service account in Google Cloud Console
   - Download the service account key as `gcp_key.json`
   - Place `gcp_key.json` in the project root directory

## Usage

1. Start the application:
```bash
python app.py
```

2. Open your browser and navigate to:
```
http://localhost:5000
```

3. Click "Start Conversation" to begin the interview
4. Speak when prompted
5. Download the transcript when finished

## Configuration

- Audio settings can be adjusted in `app.py`:
  - `RATE`: Sample rate (default: 16000)
  - `CHUNK`: Audio chunk size (default: 1024)
  - `SILENCE_THRESHOLD`: Silence detection threshold
  - `SILENCE_SECONDS`: Seconds of silence to stop recording

## Security Note

The `gcp_key.json` file contains sensitive credentials and should never be committed to version control. It is already included in `.gitignore`.

## License

[Your chosen license] 