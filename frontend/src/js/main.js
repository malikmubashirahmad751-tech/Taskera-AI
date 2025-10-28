document.addEventListener('DOMContentLoaded', () => {

    let currentUserId = null;
    const USER_ID_STORAGE_KEY = 'agentUserId';

    const API_BASE_URL = 'http://127.0.0.1:8000'; 
    const CHAT_ENDPOINT = '/api/chat';
    const UPLOAD_ENDPOINT = '/api/upload';
    const LOGO_PATH = "assets/images/logo.jpg";

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
    const currentUserIdSpan = document.getElementById('currentUserId');

    loadSession();

    chatForm.addEventListener('submit', handleChatSubmit);
    menuButton.addEventListener('click', toggleSidebar);
    sidebarOverlay.addEventListener('click', toggleSidebar);
    newSessionBtn.addEventListener('click', handleNewSession);
    chatUploadBtn.addEventListener('click', () => fileUploadInput.click());
    fileUploadInput.addEventListener('change', handleFileUpload);

    chatLog.addEventListener('click', (e) => {
        if (e.target.classList.contains('suggestion-btn')) {
            const suggestionText = e.target.innerText.replace(/"/g, '');
            userInput.value = suggestionText;
            
            userInput.focus();
        }
    });

    function loadSession() {
        const storedUserId = sessionStorage.getItem(USER_ID_STORAGE_KEY);
        if (storedUserId) {
            currentUserId = storedUserId;
            updateUserIdUI(currentUserId);
        }
    }

    function setUserId(userId) {
        if (!userId) return;
        currentUserId = userId;
        sessionStorage.setItem(USER_ID_STORAGE_KEY, userId);
        updateUserIdUI(userId);
    }

    function updateUserIdUI(userId) {
        currentUserIdSpan.textContent = userId || 'Not established';
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

        const formData = new FormData();
        formData.append('file', file);
        if (currentUserId) formData.append('user_id', currentUserId);

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

            setUserId(data.user_id);
            document.getElementById(statusId).innerHTML = `
                <svg class="w-4 h-4 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 
                    9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>
                <span>${file.name} uploaded successfully.</span>`;
            addStatusMessageToChat(`File uploaded and indexed: ${file.name}`);
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
        wrapper.className = 'flex justify-center';
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
                wrapper.querySelector('p').textContent = message;
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
              <img src="assets/images/logo.jpg" alt="Agent D. Logo" class="w-9 h-9 rounded-lg">
            </div>
            <div class="bg-neutral-800 rounded-lg rounded-tl-none p-4 max-w-lg shadow-md">
              <p class="text-sm mb-3">Hello! I'm Agent D., your AI research assistant. A new session has started. You can ask me questions or upload a document (using the paperclip icon below) for me to analyze.</p>
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

    function toggleSidebar() {
        sidebar.classList.toggle('-translate-x-full');
        
        // Toggle the main content's margin (for desktop)
        mainContent.classList.toggle('md:ml-64');
        
        // Toggle the overlay's visibility (for mobile)
        sidebarOverlay.classList.toggle('hidden');
    }

    // --- Add the initial startup message on first load ---
    // (We clear the chatLog first, just in case there's static HTML)
    chatLog.innerHTML = '';
    addStartupMessage();
});