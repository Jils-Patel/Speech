document.addEventListener('DOMContentLoaded', function() {
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const statusDiv = document.getElementById('status');
    const conversationDiv = document.getElementById('conversation');
    const progressBar = document.getElementById('progressBar');
    
    let statusCheckInterval = null;
    let listeningElement = null;
    
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
                
                // Start checking status
                startStatusCheck();
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
                stopStatusCheck();
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
    
    // Start checking conversation status
    function startStatusCheck() {
        statusCheckInterval = setInterval(checkConversationStatus, 300);
    }
    
    // Stop checking conversation status
    function stopStatusCheck() {
        if (statusCheckInterval) {
            clearInterval(statusCheckInterval);
            statusCheckInterval = null;
        }
    }
    
    // Check conversation status and update UI in real-time
    async function checkConversationStatus() {
        try {
            const response = await fetch('/conversation_status');
            const status = await response.json();
            
            // Update status text
            if (status.active) {
                if (status.is_listening) {
                    statusDiv.textContent = 'Listening...';
                    if (!listeningElement) {
                        listeningElement = document.createElement('div');
                        listeningElement.className = 'listening-indicator';
                        listeningElement.textContent = '🎤 Listening...';
                        conversationDiv.appendChild(listeningElement);
                    }
                } else {
                    statusDiv.textContent = 'Processing...';
                    if (listeningElement) {
                        listeningElement.remove();
                        listeningElement = null;
                    }
                }
                
                // Update conversation display
                updateConversationDisplay(status);
            } else if (status.completed) {
                statusDiv.textContent = 'Conversation completed!';
                stopBtn.disabled = true;
                startBtn.disabled = false;
                downloadBtn.disabled = false;
                stopStatusCheck();
                fetchTranscript();
            }
        } catch (error) {
            console.error('Error checking conversation status:', error);
        }
    }
    
    // Update conversation display
    function updateConversationDisplay(status) {
        if (status.current_question) {
            // Check if this question is already displayed
            const existingQuestions = conversationDiv.querySelectorAll('.question');
            const lastQuestion = existingQuestions[existingQuestions.length - 1];
            
            if (!lastQuestion || lastQuestion.textContent !== status.current_question) {
                // Display new question
                const questionDiv = document.createElement('div');
                questionDiv.className = 'question';
                questionDiv.textContent = status.current_question;
                conversationDiv.appendChild(questionDiv);
            }
        }
        
        if (status.current_answer) {
            // Check if this answer is already displayed
            const existingAnswers = conversationDiv.querySelectorAll('.answer');
            const lastAnswer = existingAnswers[existingAnswers.length - 1];
            
            if (!lastAnswer || lastAnswer.textContent !== status.current_answer) {
                // Display new answer
                const answerDiv = document.createElement('div');
                answerDiv.className = 'answer';
                answerDiv.textContent = status.current_answer;
                conversationDiv.appendChild(answerDiv);
            }
        }
        
            conversationDiv.scrollTop = conversationDiv.scrollHeight;
    }
    
    // Fetch transcript
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
    
    // Event listeners
    startBtn.addEventListener('click', startConversation);
    stopBtn.addEventListener('click', stopConversation);
    downloadBtn.addEventListener('click', downloadTranscript);
}); 