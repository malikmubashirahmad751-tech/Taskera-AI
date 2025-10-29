document.addEventListener('DOMContentLoaded', () => {

    let currentUserId = null;
    const USER_ID_STORAGE_KEY = 'agentUserId';

    const API_BASE_URL = 'http://127.0.0.1:8000'; 
    const CHAT_ENDPOINT = '/api/chat';
    const UPLOAD_ENDPOINT = '/api/upload';
    const LOGO_PATH = "assets/images/logo.jpg";

    // --- Get All Elements ---
    const chatLog = document.getElementById('chatLog');
    const chatForm = document.getElementById('chatForm');
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendButton');
    const menuButton = document.getElementById('menuButton');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const mainContent = document.querySelector('main'); 
    const newSessionBtn = document.getElementById('newSessionBtn');
    const chatUploadBtn = document.getElementById('chatUploadBtn');
    const fileUploadInput = document.getElementById('fileUploadInput');
    const fileUploadStatus = document.getElementById('fileUploadStatus');
    
    // --- New Elements ---
    const currentUserIdSpan = document.getElementById('currentUserId');
    const userIdInput = document.getElementById('userIdInput');
    const setUserIdBtn = document.getElementById('setUserIdBtn');
    const menuIcon = document.getElementById('menuIcon');
    const closeIcon = document.getElementById('closeIcon');

    loadSession();

    // --- Event Listeners ---
    chatForm.addEventListener('submit', handleChatSubmit);
    menuButton.addEventListener('click', toggleSidebar);
    sidebarOverlay.addEventListener('click', toggleSidebar);
    newSessionBtn.addEventListener('click', handleNewSession);
    setUserIdBtn.addEventListener('click', handleSetUserId); // New listener
    chatUploadBtn.addEventListener('click', () => fileUploadInput.click());
    fileUploadInput.addEventListener('change', handleFileUpload);

    chatLog.addEventListener('click', (e) => {
        if (e.target.classList.contains('suggestion-btn')) {
            const suggestionText = e.target.innerText.replace(/"/g, '');
            userInput.value = suggestionText;
            userInput.focus();
        }
    });

    // --- Functions ---

    function loadSession() {
        const storedUserId = sessionStorage.getItem(USER_ID_STORAGE_KEY);
        if (storedUserId) {
            setUserId(storedUserId); // Use setUserId to ensure UI updates
        }
    }

    function setUserId(userId) {
        if (!userId || typeof userId !== 'string' || userId.trim().length === 0) {
            console.warn("Invalid User ID passed to setUserId");
            return;
        }
        currentUserId = userId.trim();
        sessionStorage.setItem(USER_ID_STORAGE_KEY, currentUserId);
        updateUserIdUI(currentUserId);
    }

    function updateUserIdUI(userId) {
        currentUserIdSpan.textContent = userId || 'Not established';
        if (userId) {
            userIdInput.value = ''; // Clear input if setting was successful
        }
    }

    // --- New Function ---
    // Handles the "Set ID" button click
    function handleSetUserId() {
        const newUserId = userIdInput.value.trim();
        if (newUserId) {
            // Clear the chat log
            chatLog.innerHTML = '';
            // Set the new user ID
            setUserId(newUserId);
            // Add a status message
            addStatusMessageToChat(`Session loaded for User ID: ${newUserId}`);
            // Add the startup message
            addStartupMessage();
            // Close the sidebar
            toggleSidebar(false); // Force close
        }
    }

    async function handleNewSession() {
        if (currentUserId) {
            addStatusMessageToChat('Clearing session data on server...');
            try {
                const response = await fetch(`${API_BASE_URL}/users/${currentUserId}/data`, { method: 'DELETE' });
                const data = await response.json().catch(() => ({}));
                addStatusMessageToChat(data.message || 'Server session cleared.');
            } catch (error) {
                addStatusMessageToChat(`Error clearing session: ${error.message}`);
            }
        }

        sessionStorage.removeItem(USER_ID_STORAGE_KEY);
        currentUserId = null;
        updateUserIdUI(null);
        chatLog.innerHTML = '';
        addStartupMessage();
        fileUploadStatus.innerHTML = '';
    }

    async function handleChatSubmit(e) {
        e.preventDefault(); 
        const message = userInput.value.trim();
        if (!message) return;

        addMessageToChat('user', message);
        userInput.value = '';
        toggleForm(false);
        addMessageToChat('ai', '...', 'typing');

        try {
            if (!currentUserId) setUserId(crypto.randomUUID());

            const response = await fetch(`${API_BASE_URL}${CHAT_ENDPOINT}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: message, user_id: currentUserId })
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                const detail = data.detail || `${response.status} ${response.statusText}`;
                throw new Error(detail);
            }

            console.log(" API Response:", data);

            const aiResponse =
                data.answer ||
                data.response ||
                data.message ||
                data.output ||
                data.result ||
                (typeof data === 'string' ? data : null);

            if (data.user_id) setUserId(data.user_id);
            
            removeTypingIndicator();

            if (aiResponse) {
                addMessageToChat('ai', aiResponse);
            } else {
                addMessageToChat('ai', ' No readable response from backend.');
            }

        } catch (error) {
            console.error(' Error fetching AI response:', error);
            removeTypingIndicator();
            addMessageToChat('ai', ` Error: ${error.message}`);
        } finally {
            toggleForm(true);
            userInput.focus();
        }
    }

    async function handleFileUpload(e) {
        const file = e.target.files[0];
        if (!file) return;

        // --- Use new UUID if no session exists ---
        if (!currentUserId) setUserId(crypto.randomUUID());

        const formData = new FormData();
        formData.append('file', file);
        formData.append('user_id', currentUserId); // currentUserId is guaranteed to be set

        const statusId = `file-${Date.now()}`;
        fileUploadStatus.innerHTML = `
            <div id="${statusId}" class="flex items-center space-x-2 text-xs">
                <div class="upload-spinner"></div>
                <span>Uploading ${file.name}...</span>
            </div>`;

        try {
            const response = await fetch(`${API_BASE_URL}${UPLOAD_ENDPOINT}`, { method: 'POST', body: formData });
            const data = await response.json().catch(() => ({}));

            if (!response.ok) throw new Error(data.detail || 'File upload failed.');

            setUserId(data.user_id); // API might return a new ID if one wasn't sent
            
            const statusElement = document.getElementById(statusId);
            statusElement.innerHTML = `
                <svg class="w-4 h-4 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 
                    9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>
                <span>${data.message || `${file.name} processed.`}</span>`;

            if (data.file_details) {
                const uploadTime = new Date(data.file_details.upload_time).toLocaleTimeString();
                addStatusMessageToChat(
                    `File: ${data.file_details.name} (Uploaded by: ${data.file_details.uploaded_by} at ${uploadTime})`
                );
            }

            if (data.extracted_text) {
                addMessageToChat('ai', data.extracted_text);
                if (data.follow_up_prompt) {
                    addMessageToChat('ai', data.follow_up_prompt);
                }
            } 
            else if (data.note) {
                addStatusMessageToChat(data.note);
            }

        } catch (error) {
            document.getElementById(statusId).innerHTML = `
                <svg class="w-4 h-4 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 
                    8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 
                    1.414L8.586 10l-1.293 1.293a1 1 0 
                    101.414 1.414L10 11.414l1.293 
                    1.293a1 1 0 001.414-1.414L11.414 
                    10l1.293-1.293a1 1 0 00-1.414-1.414L10 
                    8.586 8.707 7.293z" clip-rule="evenodd"></path></svg>
                <span>Error uploading ${file.name}.</span>`;
            addStatusMessageToChat(`Error uploading file: ${error.message}`);
        } finally {
            e.target.value = null; 
        }
    }

    function addStatusMessageToChat(message) {
        const wrapper = document.createElement('div');
        wrapper.className = 'flex justify-center my-2'; // Added margin
        wrapper.innerHTML = `
            <div class="text-xs text-neutral-500 italic px-4 py-1 bg-neutral-800 rounded-full">
                ${message.replace(/</g, "&lt;").replace(/>/g, "&gt;")}
            </div>`;
        chatLog.appendChild(wrapper);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    function addMessageToChat(sender, message, type = 'message') {
        const wrapper = document.createElement('div');

        if (sender === 'user') {
            wrapper.className = 'flex justify-end mb-2';
            wrapper.innerHTML = `
                <div class="flex items-start space-x-3 max-w-lg">
                    <div class="bg-fuchsia-700 text-white rounded-lg rounded-tr-none p-4 shadow-md">
                        <p class="text-sm"></p>
                    </div>
                    <div class="w-9 h-9 rounded-full bg-purple-700 flex items-center justify-center font-semibold flex-shrink-0">U</div>
                </div>`;
            wrapper.querySelector('p').textContent = message;
        } else {
            wrapper.className = 'flex items-start space-x-3 mb-2';
            if (type === 'typing') {
                wrapper.id = 'typing-indicator';
                wrapper.innerHTML = `
                    <div class="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0">
                        <img src="${LOGO_PATH}" alt="Agent Logo" class="w-9 h-9 rounded-lg">
                    </div>
                    <div class="bg-neutral-800 rounded-lg rounded-tl-none p-4 shadow-md">
                        <div class="flex space-x-1">
                            <div class="w-2 h-2 bg-neutral-400 rounded-full typing-dot"></div>
                            <div class="w-2 h-2 bg-neutral-400 rounded-full typing-dot"></div>
                            <div class="w-2 h-2 bg-neutral-400 rounded-full typing-dot"></div>
                        </div>
                    </div>`;
            } else {
                wrapper.innerHTML = `
                    <div class="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0">
                        <img src="${LOGO_PATH}" alt="Agent Logo" class="w-9 h-9 rounded-lg">
                    </div>
                    <div class="bg-neutral-800 rounded-lg rounded-tl-none p-4 max-w-lg shadow-md">
                        <p class="text-sm"></p>
                    </div>`;
                wrapper.querySelector('p').innerText = message;
            }
        }
        chatLog.appendChild(wrapper);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    function addStartupMessage() {
        const wrapper = document.createElement('div');
        wrapper.className = 'flex items-start space-x-3';
        wrapper.innerHTML = `
            <div class="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0">
              <img src="assets/images/logo.jpg" alt="Devis AI Logo" class="w-9 h-9 rounded-lg">
            </div>
            <div class="bg-neutral-800 rounded-lg rounded-tl-none p-4 max-w-lg shadow-md">
              <p class="text-sm mb-3">Hello! I'm Devis AI, your AI research assistant. A new session has started. You can ask me questions or upload a document (using the paperclip icon below) for me to analyze.</p>
              <p class="text-sm font-medium mb-3 text-neutral-300">Here are some things you can try:</p>
              <ul class="list-none space-y-2">
                <li><button class="suggestion-btn">"Summarize the uploaded document."</button></li>
                <li><button class="suggestion-btn">"What are the key findings about [topic]?"</button></li>
                <li><button class="suggestion-btn">"Draft an email to my team about..."</button></li>
              </ul>
            </div>`;
        chatLog.appendChild(wrapper);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    function removeTypingIndicator() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) typingIndicator.remove();
    }

    function toggleForm(isEnabled) {
        userInput.disabled = !isEnabled;
        sendButton.disabled = !isEnabled;
        chatUploadBtn.disabled = !isEnabled;
    }

    // --- Updated Function ---
    // Can now be forced open or closed by passing a boolean
    function toggleSidebar(forceState) {
        const isOpen = !sidebar.classList.contains('-translate-x-full');
        
        // Determine the new state
        let newState = !isOpen; // Default is to toggle
        if (typeof forceState === 'boolean') {
            newState = forceState; // Use forced state if provided
        }

        // Apply new state
        if (newState) {
            // Open sidebar
            sidebar.classList.remove('-translate-x-full');
            mainContent.classList.add('md:ml-64');
            sidebarOverlay.classList.remove('hidden');
            menuIcon.classList.add('hidden');
            closeIcon.classList.remove('hidden');
        } else {
            // Close sidebar
            sidebar.classList.add('-translate-x-full');
            mainContent.classList.remove('md:ml-64');
            sidebarOverlay.classList.add('hidden');
            menuIcon.classList.remove('hidden');
            closeIcon.classList.add('hidden');
        }
    }

    // --- Initial Load ---
    chatLog.innerHTML = '';
    addStartupMessage();
});
