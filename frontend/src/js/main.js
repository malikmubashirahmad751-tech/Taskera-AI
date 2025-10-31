document.addEventListener('DOMContentLoaded', () => {

    let currentUserId = null;
    const USER_ID_STORAGE_KEY = 'agentUserId';
    
    let stagedFiles = [];
    const MAX_FILES = 10;

    const API_BASE_URL = 'http://127.0.0.1:8000'; 
    const CHAT_ENDPOINT = '/api/chat';
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
    
    const filePreviewContainer = document.getElementById('filePreviewContainer');
    
    const currentUserIdSpan = document.getElementById('currentUserId');
    const userIdInput = document.getElementById('userIdInput');
    const setUserIdBtn = document.getElementById('setUserIdBtn');
    const menuIcon = document.getElementById('menuIcon');
    const closeIcon = document.getElementById('closeIcon');

    loadSession();

    chatForm.addEventListener('submit', handleChatSubmit); 
    menuButton.addEventListener('click', toggleSidebar);
    sidebarOverlay.addEventListener('click', toggleSidebar);
    newSessionBtn.addEventListener('click', handleNewSession);
    setUserIdBtn.addEventListener('click', handleSetUserId);
    chatUploadBtn.addEventListener('click', () => fileUploadInput.click());
    fileUploadInput.addEventListener('change', handleFileStage); 

    filePreviewContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('file-chip-remove') || e.target.closest('.file-chip-remove')) {
            const button = e.target.classList.contains('file-chip-remove') ? e.target : e.target.closest('.file-chip-remove');
            const fileId = button.dataset.fileId;
            if (fileId) {
                removeStagedFile(fileId);
            }
        }
    });

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
            setUserId(storedUserId);
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
            userIdInput.value = '';
        }
    }

    function handleSetUserId() {
        const newUserId = userIdInput.value.trim();
        if (newUserId) {
            chatLog.innerHTML = '';
            setUserId(newUserId);
            addStatusMessageToChat(`Session loaded for User ID: ${newUserId}`);
            addStartupMessage();
            toggleSidebar(false);
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
        clearStagedFiles(); 
    }

    function handleFileStage(e) {
        const files = e.target.files;
        if (!files) return;

        if (stagedFiles.length + files.length > MAX_FILES) {
            alert(`You can only upload a maximum of ${MAX_FILES} files.`);
            e.target.value = null;
            return;
        }

        for (const file of files) {
            const fileId = crypto.randomUUID();
            const fileWithId = { id: fileId, file: file };
            stagedFiles.push(fileWithId);
            addFileChip(fileWithId);
        }
        
        e.target.value = null; 
    }

    function addFileChip(fileWithId) {
        const file = fileWithId.file;
        const fileId = fileWithId.id;
        
        filePreviewContainer.style.display = 'flex'; 

        const chip = document.createElement('div');
        chip.className = 'file-chip';
        chip.id = `file-chip-${fileId}`; 

        const removeButtonHtml = `<button type="button" class="file-chip-remove" data-file-id="${fileId}">&times;</button>`;
        const fileNameHtml = `<span class="file-chip-name">${file.name.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</span>`;

        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = (event) => {
                chip.innerHTML = `
                    <img src="${event.target.result}" alt="Preview" class="w-8 h-8 rounded object-cover mr-2">
                    ${fileNameHtml}
                    ${removeButtonHtml}
                `;
            };
            reader.readAsDataURL(file);
        } else {
            chip.innerHTML = `
                ${fileNameHtml}
                ${removeButtonHtml}
            `;
        }
        
        filePreviewContainer.appendChild(chip);
    }

    function removeStagedFile(fileId) {
        stagedFiles = stagedFiles.filter(f => f.id !== fileId);
        
        const chip = document.getElementById(`file-chip-${fileId}`);
        if (chip) {
            chip.remove();
        }

        if (stagedFiles.length === 0) {
            filePreviewContainer.style.display = 'none';
        }
    }


    function clearStagedFiles() {
        stagedFiles = [];
        filePreviewContainer.innerHTML = '';
        filePreviewContainer.style.display = 'none';
        fileUploadInput.value = null;
    }


    async function handleChatSubmit(e) {
        e.preventDefault(); 
        const message = userInput.value.trim();
        
        if (!message && stagedFiles.length === 0) return;

        if (!currentUserId) setUserId(crypto.randomUUID());

        const formData = new FormData();
        formData.append('query', message);
        formData.append('user_id', currentUserId);
        
        const fileNames = [];
        for (const fileWithId of stagedFiles) {
            formData.append('files', fileWithId.file, fileWithId.file.name);
            fileNames.push(fileWithId.file.name);
        }
        
        if (fileNames.length > 0) {
            addMessageToChat('user', message, fileNames); 
        } else {
            addMessageToChat('user', message, null);
        }

        userInput.value = '';
        clearStagedFiles(); 
        toggleForm(false);
        addMessageToChat('ai', '...', 'typing');

        try {
            const response = await fetch(`${API_BASE_URL}${CHAT_ENDPOINT}`, {
                method: 'POST',
                body: formData 
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
    
    
    function addStatusMessageToChat(message) {
        const wrapper = document.createElement('div');
        wrapper.className = 'flex justify-center my-2';
        wrapper.innerHTML = `
            <div class="text-xs text-neutral-500 italic px-4 py-1 bg-neutral-800 rounded-full">
                ${message.replace(/</g, "&lt;").replace(/>/g, "&gt;")}
            </div>`;
        chatLog.appendChild(wrapper);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    function addMessageToChat(sender, message, fileNames = null, type = 'message') {
        const wrapper = document.createElement('div');

        if (sender === 'user') {
            wrapper.className = 'flex justify-end mb-2';
            
            let fileChipsHtml = '';
            if (fileNames && fileNames.length > 0) {
                const chips = fileNames.map(name => `
                    <span class="text-xs px-3 py-1 bg-purple-800 rounded-full">
                        ${name.replace(/</g, "&lt;").replace(/>/g, "&gt;")}
                    </span>
                `).join('');
                
                fileChipsHtml = `
                    <div class="mt-2 border-t border-fuchsia-800 pt-2 flex flex-wrap gap-2">
                        ${chips}
                    </div>`;
            }

            wrapper.innerHTML = `
                <div class="flex items-start space-x-3 max-w-lg">
                    <div class="bg-fuchsia-700 text-white rounded-lg rounded-tr-none p-4 shadow-md">
                        <p class="text-sm"></p>
                        ${fileChipsHtml}
                    </div>
                    <div class="w-9 h-9 rounded-full bg-purple-700 flex items-center justify-center font-semibold flex-shrink-0">U</div>
                </div>`;
            
            if (message) {
                wrapper.querySelector('p').textContent = message;
            } else {
                wrapper.querySelector('p').remove(); 
            }

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
              <p class="text-sm mb-3">Hello! I'm Devis AI, your AI research assistant. A new session has started. You can ask me questions or upload documents (using the paperclip icon below) for me to analyze.</p>
              <p class="text-sm font-medium mb-3 text-neutral-300">Here are some things you can try:</p>
              <ul class="list-none space-y-2">
                <li><button class="suggestion-btn">"Summarize the uploaded document(s)."</button></li>
                <li><button class="suggestion-btn">"What are the key findings about [topic]?"</button></li>
                <li><button class="suggestion-btn">"Compare the contents of the uploaded files."</button></li>
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

    function toggleSidebar(forceState) {
        const isOpen = !sidebar.classList.contains('-translate-x-full');
        let newState = !isOpen;
        if (typeof forceState === 'boolean') {
            newState = forceState;
        }
        if (newState) {
            sidebar.classList.remove('-translate-x-full');
            mainContent.classList.add('md:ml-64');
            sidebarOverlay.classList.remove('hidden');
            menuIcon.classList.add('hidden');
            closeIcon.classList.remove('hidden');
        } else {
            sidebar.classList.add('-translate-x-full');
            mainContent.classList.remove('md:ml-64');
            sidebarOverlay.classList.add('hidden');
            menuIcon.classList.remove('hidden');
            closeIcon.classList.add('hidden');
        }
    }

    chatLog.innerHTML = '';
    addStartupMessage();
});