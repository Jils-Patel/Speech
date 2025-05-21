document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const conversationDiv = document.getElementById('conversation');
    const statusDiv = document.getElementById('status');
    const progressBar = document.getElementById('progressBar');
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    
    // Variables
    let questions = [];
    let statusCheckInterval = null;
    let lastQuestionIndex = -1;
    let currentQuestionElement = null;
    let currentAnswerElement = null;
    let listeningElement = null;
    let lastAnswer = null;
    
    // Fetch questions from server
    async function fetchQuestions() {
        try {
            const response = await fetch('/get_questions');
            const data = await response.json();
            questions = data.questions || [];
            return questions.length > 0;
        } catch (error) {
            console.error('Error fetching questions:', error);
            statusDiv.textContent = 'Failed to load questions. Please refresh.';
            return false;
        }
    }
    
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
                lastQuestionIndex = -1;
                lastAnswer = null;
                
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
            
            // Update progress bar
            if (status.total_questions > 0) {
                const progress = (status.current_question_index / status.total_questions) * 100;
                progressBar.style.width = `${progress}%`;
            }
            
            // Update status text
            if (status.active) {
                if (status.current_question_index < status.total_questions) {
                    statusDiv.textContent = `Question ${status.current_question_index + 1} of ${status.total_questions}`;
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
    
    // Update the conversation display in real-time
    function updateConversationDisplay(status) {
        // Check if we have a new question
        if (status.current_question && status.current_question_index > lastQuestionIndex) {
            lastQuestionIndex = status.current_question_index;
            lastAnswer = null;
            
            // Remove any previous current question/answer elements
            if (currentQuestionElement) {
                currentQuestionElement.className = 'question';
            }
            if (currentAnswerElement) {
                currentAnswerElement.className = 'answer';
                currentAnswerElement = null;
            }
            
            // Create new current question element
            currentQuestionElement = document.createElement('div');
            currentQuestionElement.className = 'current-question';
            currentQuestionElement.textContent = status.current_question;
            conversationDiv.appendChild(currentQuestionElement);
            
            // Scroll to bottom
            conversationDiv.scrollTop = conversationDiv.scrollHeight;
        }
        
        // Update listening indicator
        if (status.is_listening) {
            if (!listeningElement) {
                listeningElement = document.createElement('div');
                listeningElement.className = 'listening';
                listeningElement.textContent = 'Listening...';
                conversationDiv.appendChild(listeningElement);
                conversationDiv.scrollTop = conversationDiv.scrollHeight;
            }
        } else {
            if (listeningElement) {
                listeningElement.remove();
                listeningElement = null;
            }
        }
        
        // Check if we have a new answer
        if (status.current_answer && status.current_answer !== lastAnswer) {
            lastAnswer = status.current_answer;
            
            // Create answer element if it doesn't exist
            if (!currentAnswerElement) {
                currentAnswerElement = document.createElement('div');
                currentAnswerElement.className = 'current-answer';
                conversationDiv.appendChild(currentAnswerElement);
            }
            
            // Update answer text
            currentAnswerElement.textContent = status.current_answer;
            
            // Scroll to bottom
            conversationDiv.scrollTop = conversationDiv.scrollHeight;
        }
        
        // Update status text
        if (status.is_listening) {
            statusDiv.textContent = 'Listening...';
        } else if (status.current_answer) {
            statusDiv.textContent = `Question ${status.current_question_index + 1} of ${status.total_questions}`;
        }
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
        // Simply redirect to the download endpoint
        window.location.href = '/download_transcript';
    }
    
    // Event listeners
    startBtn.addEventListener('click', async function() {
        // Fetch questions if needed
        if (questions.length === 0) {
            const hasQuestions = await fetchQuestions();
            if (!hasQuestions) {
                return;
            }
        }
        
        // Start conversation
        startConversation();
    });
    
    stopBtn.addEventListener('click', function() {
        stopConversation();
    });
    
    downloadBtn.addEventListener('click', function() {
        downloadTranscript();
    });
}); 