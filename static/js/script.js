document.addEventListener('DOMContentLoaded', function() {
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const statusDiv = document.getElementById('status');
    const conversationDiv = document.getElementById('conversation');
    const progressBar = document.getElementById('progressBar');
    
    let listeningElement = null;
    
    // Initialize Socket.IO connection
    const socket = io();
    
    // Socket.IO event listeners
    socket.on('connect', function() {
        console.log('Connected to server');
    });
    
    socket.on('disconnect', function() {
        console.log('Disconnected from server');
    });
    
    // Listen for speech events
    socket.on('listening_started', function(data) {
        statusDiv.textContent = 'Listening...';
        if (!listeningElement) {
            listeningElement = document.createElement('div');
            listeningElement.className = 'listening-indicator';
            listeningElement.textContent = '🎤 Listening...';
            conversationDiv.appendChild(listeningElement);
        }
    });
    
    socket.on('speech_detected', function(data) {
        statusDiv.textContent = 'Speech detected...';
        
        // Update progress bar to show activity
        animateProgressBar(30);
    });
    
    socket.on('speech_ended', function(data) {
        statusDiv.textContent = 'Processing speech...';
        if (listeningElement) {
            listeningElement.remove();
            listeningElement = null;
        }
        
        // Update progress bar
        animateProgressBar(60);
    });
    
    socket.on('transcription_complete', function(data) {
        statusDiv.textContent = 'Transcription complete';
        
        // Create and display user's answer
        const text = data.text || '';
        const answerDiv = document.createElement('div');
        answerDiv.className = 'answer';
        answerDiv.textContent = text;
        conversationDiv.appendChild(answerDiv);
        
        // Update progress bar
        animateProgressBar(80);
        
        // Scroll to bottom
        conversationDiv.scrollTop = conversationDiv.scrollHeight;
    });
    
    socket.on('processing_user_input', function(data) {
        statusDiv.textContent = 'Processing your response...';
    });
    
    socket.on('agent_speaking', function(data) {
        statusDiv.textContent = 'Agent speaking...';
        
        // Create and display agent's question
        const text = data.text || '';
        const questionDiv = document.createElement('div');
        questionDiv.className = 'question';
        questionDiv.textContent = text;
        conversationDiv.appendChild(questionDiv);
        
        // Update progress bar
        animateProgressBar(100);
        
        // Scroll to bottom
        conversationDiv.scrollTop = conversationDiv.scrollHeight;
    });
    
    socket.on('agent_finished_speaking', function() {
        statusDiv.textContent = 'Your turn to speak';
        
        // Reset progress bar for next interaction
        animateProgressBar(0);
    });
    
    socket.on('conversation_ended', function(data) {
        statusDiv.textContent = 'Conversation completed!';
        stopBtn.disabled = true;
        startBtn.disabled = false;
        downloadBtn.disabled = false;
        
        // Remove listening indicator if present
        if (listeningElement) {
            listeningElement.remove();
            listeningElement = null;
        }
    });
    
    socket.on('transcript_saved', function(data) {
        statusDiv.textContent = `Transcript saved as ${data.filename}`;
    });
    
    socket.on('no_speech_detected', function() {
        statusDiv.textContent = 'No speech detected. Please try again.';
        if (listeningElement) {
            listeningElement.remove();
            listeningElement = null;
        }
    });
    
    socket.on('conversation_error', function(data) {
        statusDiv.textContent = `Error: ${data.error || 'Unknown error'}`;
        console.error('Conversation error:', data.error);
    });
    
    // Start conversation
    async function startConversation() {
        try {
            const response = await fetch('/start_conversation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            if (data.success) {
                statusDiv.textContent = 'Conversation started. Please speak when prompted.';
                startBtn.disabled = true;
                stopBtn.disabled = false;
                conversationDiv.innerHTML = '';
                downloadBtn.disabled = true;
            } else {
                statusDiv.textContent = 'Failed to start conversation';
            }
        } catch (error) {
            console.error('Error starting conversation:', error);
            statusDiv.textContent = 'Failed to start conversation';
        }
    }
    
    // Stop conversation
    async function stopConversation() {
        try {
            const response = await fetch('/stop_conversation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            if (data.success) {
                statusDiv.textContent = 'Conversation stopped.';
                startBtn.disabled = false;
                stopBtn.disabled = true;
                downloadBtn.disabled = false;
                
                // Remove any listening indicator
                if (listeningElement) {
                    listeningElement.remove();
                    listeningElement = null;
                }
            } else {
                statusDiv.textContent = 'Failed to stop conversation';
            }
        } catch (error) {
            console.error('Error stopping conversation:', error);
            statusDiv.textContent = 'Failed to stop conversation';
        }
    }
    
    // Fetch transcript if needed
    async function fetchTranscript() {
        try {
            const response = await fetch('/get_transcript');
            const data = await response.json();
            const transcript = data.transcript || [];
            
            // Display transcript
            conversationDiv.innerHTML = '';
            transcript.forEach(item => {
                // Display question
                const questionDiv = document.createElement('div');
                questionDiv.className = 'question';
                questionDiv.textContent = item.question;
                conversationDiv.appendChild(questionDiv);
                
                // Display answer
                const answerDiv = document.createElement('div');
                answerDiv.className = 'answer';
                answerDiv.textContent = item.answer;
                conversationDiv.appendChild(answerDiv);
            });
            
            conversationDiv.scrollTop = conversationDiv.scrollHeight;
        } catch (error) {
            console.error('Error fetching transcript:', error);
        }
    }
    
    // Download transcript
    function downloadTranscript() {
        window.location.href = '/download_transcript';
    }
    
    // Animate progress bar
    function animateProgressBar(percentage) {
        progressBar.style.width = percentage + '%';
    }
    
    // Event listeners
    startBtn.addEventListener('click', startConversation);
    stopBtn.addEventListener('click', stopConversation);
    downloadBtn.addEventListener('click', downloadTranscript);
}); 