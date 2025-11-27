document.addEventListener('DOMContentLoaded', () => {
    
    const API_BASE_URL = 'http://127.0.0.1:8000';
    const CHAT_ENDPOINT = '/api/chat';
    
    const KEYS = {
        AUTH_TOKEN: 'taskera_access_token',
        USER_ID: 'taskera_user_id',
        USER_EMAIL: 'taskera_user_email',
        GUEST_ID: 'taskera_guest_id'
    };

    const MAX_FILES = 10;
    const MAX_FILE_SIZE_MB = 10;

    
    let state = {
        currentUserId: null,
        authToken: null,
        csrfToken: '',
        stagedFiles: [],
        isLoginMode: true,
        isProcessing: false
    };

   
    const dom = {
        sidebar: document.getElementById('sidebar'),
        sidebarOverlay: document.getElementById('sidebarOverlay'),
        menuButton: document.getElementById('menuButton'),
        closeIcon: document.getElementById('closeIcon'),
        menuIcon: document.getElementById('menuIcon'),
        
        chatLog: document.getElementById('chatLog'),
        welcomeScreen: document.getElementById('welcome-screen') || document.getElementById('welcomeScreen'),
        chatForm: document.getElementById('chatForm'),
        userInput: document.getElementById('userInput'),
        sendButton: document.getElementById('sendButton'),
        
        chatUploadBtn: document.getElementById('chatUploadBtn'),
        fileUploadInput: document.getElementById('fileUploadInput'),
        filePreviewContainer: document.getElementById('filePreviewContainer'),
        
        newSessionBtn: document.getElementById('newSessionBtn'),
        currentUserIdDisplay: document.getElementById('currentUserId'),
        
        userProfileSection: document.getElementById('userProfileSection'),
        guestAuthSection: document.getElementById('guestAuthSection'),
        userEmailDisplay: document.getElementById('userEmailDisplay'),
        logoutBtn: document.getElementById('logoutBtn'),
        openLoginModalBtn: document.getElementById('openLoginModalBtn'),
        
        authModal: document.getElementById('authModal'),
        authForm: document.getElementById('authForm'),
        closeAuthModal: document.getElementById('closeAuthModal'),
        authEmail: document.getElementById('authEmail'),
        authPassword: document.getElementById('authPassword'),
        authSwitchBtn: document.getElementById('authSwitchBtn'),
        authSubmitBtn: document.getElementById('authSubmitBtn'),
        authModalTitle: document.getElementById('authModalTitle'),
        authErrorMsg: document.getElementById('authErrorMsg'),
        authSwitchText: document.getElementById('authSwitchText'),
    };

        function init() {
        handleGoogleLoginRedirect();
        loadSession();
        fetchCsrfToken();
        setupEventListeners();
        setupSuggestionCards();
        updateUIState();
        
        console.log('✓ Taskera AI initialized');
    }

    
    function handleGoogleLoginRedirect() {
        const urlParams = new URLSearchParams(window.location.search);
        
        if (urlParams.get('google_auth') === 'success') {
            const token = urlParams.get('access_token');
            const email = urlParams.get('email');
            const userId = urlParams.get('user_id');

            if (token && email && userId) {
                localStorage.setItem(KEYS.AUTH_TOKEN, token);
                localStorage.setItem(KEYS.USER_ID, userId);
                localStorage.setItem(KEYS.USER_EMAIL, email);
                
                state.authToken = token;
                state.currentUserId = userId;
                
                updateAuthUI(true, email);
                
                console.log(" Google Login Successful:", email);
                
                window.history.replaceState({}, document.title, window.location.pathname);
                
                addSystemMessage("Successfully logged in with Google!");
            }
        } else if (urlParams.get('google_auth') === 'error') {
            const reason = urlParams.get('reason') || 'unknown';
            console.error(" Google Login Failed:", reason);
            addSystemMessage("Google login failed. Please try again.");
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    }

    
    function loadSession() {
        const storedToken = localStorage.getItem(KEYS.AUTH_TOKEN);
        const storedUserId = localStorage.getItem(KEYS.USER_ID);
        const storedEmail = localStorage.getItem(KEYS.USER_EMAIL);

        if (storedToken && storedUserId) {
            state.authToken = storedToken;
            state.currentUserId = storedUserId;
            updateAuthUI(true, storedEmail);
            console.log('✓ Session restored:', storedUserId);
        } else {
            let guestId = localStorage.getItem(KEYS.GUEST_ID);
            if (!guestId) {
                guestId = 'guest_' + generateUUID();
                localStorage.setItem(KEYS.GUEST_ID, guestId);
            }
            state.currentUserId = guestId;
            updateAuthUI(false);
            console.log('✓ Guest session:', guestId);
        }
        
        if (dom.currentUserIdDisplay) {
            dom.currentUserIdDisplay.textContent = state.currentUserId.substring(0, 20) + '...';
        }
    }

    
    function setupEventListeners() {
        if(dom.menuButton) dom.menuButton.addEventListener('click', toggleSidebar);
        if(dom.sidebarOverlay) dom.sidebarOverlay.addEventListener('click', () => toggleSidebar(false));
        
        if(dom.chatForm) dom.chatForm.addEventListener('submit', handleChatSubmit);
        if(dom.userInput) {
            dom.userInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (!state.isProcessing) {
                        handleChatSubmit(e);
                    }
                }
            });
        }
        
        if(dom.chatUploadBtn) dom.chatUploadBtn.addEventListener('click', () => {
            if (!state.isProcessing) {
                dom.fileUploadInput.click();
            }
        });
        if(dom.fileUploadInput) dom.fileUploadInput.addEventListener('change', handleFileStage);
        if(dom.filePreviewContainer) dom.filePreviewContainer.addEventListener('click', handleFileRemove);
        
        if(dom.newSessionBtn) dom.newSessionBtn.addEventListener('click', handleNewSession);
        
        if(dom.openLoginModalBtn) dom.openLoginModalBtn.addEventListener('click', () => showAuthModal(true));
        if(dom.closeAuthModal) dom.closeAuthModal.addEventListener('click', hideAuthModal);
        if(dom.authSwitchBtn) dom.authSwitchBtn.addEventListener('click', toggleAuthMode);
        if(dom.authForm) dom.authForm.addEventListener('submit', handleAuthSubmit);
        if(dom.logoutBtn) dom.logoutBtn.addEventListener('click', handleLogout);
        
        if(dom.authModal) {
            dom.authModal.addEventListener('click', (e) => { 
                if (e.target === dom.authModal) hideAuthModal(); 
            });
        }
    }

    function setupSuggestionCards() {
        const cards = document.querySelectorAll('.suggestion-card');
        cards.forEach(card => {
            card.addEventListener('click', () => {
                if (state.isProcessing) return;
                
                const textSpan = card.querySelector('span.text-zinc-200') || card.querySelector('h3');
                if (textSpan) {
                    dom.userInput.value = textSpan.textContent.trim();
                    dom.userInput.focus();
                }
            });
        });
    }

    
    async function handleChatSubmit(e) {
        if(e) e.preventDefault();
        
        if (state.isProcessing) {
            console.log('Already processing request');
            return;
        }
        
        const message = dom.userInput.value.trim();
        const hasFiles = state.stagedFiles.length > 0;
        
        if (!message && !hasFiles) return;
        
        const fileNames = state.stagedFiles.map(f => f.file.name);
        addMessageToChat('user', message, hasFiles ? fileNames : null);
        
        if(dom.welcomeScreen) dom.welcomeScreen.classList.add('hidden');

        const formData = new FormData();
        formData.append('query', message);
        formData.append('user_id', state.currentUserId);
        
        const userEmail = localStorage.getItem(KEYS.USER_EMAIL);
        if (userEmail) {
            formData.append('email', userEmail);
        }
        
        state.stagedFiles.forEach(f => formData.append('files', f.file));

        dom.userInput.value = '';
        clearStagedFiles();
        setProcessing(true);
        addTypingIndicator();

        try {
            const headers = { 'x-csrftoken': state.csrfToken };
            if (state.authToken) {
                headers['Authorization'] = `Bearer ${state.authToken}`;
            }

            const response = await fetch(`${API_BASE_URL}${CHAT_ENDPOINT}`, {
                method: 'POST',
                headers: headers,
                body: formData
            });

            removeTypingIndicator();

            if (response.status === 402) {
                addSystemMessage("Free trial limit reached. Please sign in to continue.");
                showAuthModal(false, "Guest limit reached. Create an account to continue.");
                return;
            }
            
            if (response.status === 401) {
                handleLogout();
                showAuthModal(true, "Session expired. Please log in again.");
                return;
            }

            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || `Error: ${response.status}`);
            }

            let aiResponse = data.answer || data.response || JSON.stringify(data, null, 2);
            if (Array.isArray(aiResponse)) {
                aiResponse = aiResponse.join('\n');
            }
            
            addMessageToChat('ai', aiResponse);

        } catch (error) {
            removeTypingIndicator();
            console.error('Chat error:', error);
            addSystemMessage(`Error: ${error.message}`);
        } finally {
            setProcessing(false);
        }
    }

    
    function addMessageToChat(sender, message, fileNames = null) {
        const wrapper = document.createElement('div');
        wrapper.className = `chat-message-wrapper w-full flex ${sender === 'user' ? 'justify-end' : 'justify-start'} mb-6 animate-fade-in`;
        
        if (sender === 'user') {
            wrapper.innerHTML = `
                <div class="flex flex-col items-end max-w-[85%] md:max-w-2xl">
                    <div class="bg-zinc-800 text-white rounded-2xl rounded-tr-sm px-5 py-3.5 shadow-md border border-zinc-700/50">
                        <p class="text-sm leading-relaxed whitespace-pre-wrap">${escapeHtml(message)}</p>
                        ${renderFileAttachments(fileNames)}
                    </div>
                </div>`;
        } else {
            wrapper.innerHTML = `
                <div class="flex items-start space-x-4 max-w-full md:max-w-3xl">
                    <div class="flex-shrink-0 mt-1">
                        <img src="assets/images/logo.png" onerror="this.src='https://via.placeholder.com/32'" alt="Taskera AI" class="w-8 h-8 rounded-lg shadow-sm">
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="prose prose-invert prose-sm max-w-none text-zinc-300 leading-relaxed">
                            ${formatAIResponse(message)}
                        </div>
                    </div>
                </div>`;
        }
        
        dom.chatLog.appendChild(wrapper);
        scrollToBottom();
    }

    function addSystemMessage(text) {
        const wrapper = document.createElement('div');
        wrapper.className = 'chat-message-wrapper flex justify-center my-4';
        wrapper.innerHTML = `<span class="text-xs text-zinc-500 bg-zinc-900/50 border border-zinc-800 px-3 py-1 rounded-full">${escapeHtml(text)}</span>`;
        dom.chatLog.appendChild(wrapper);
        scrollToBottom();
    }

    function addTypingIndicator() {
        removeTypingIndicator(); 
        
        const wrapper = document.createElement('div');
        wrapper.id = 'typing-indicator';
        wrapper.className = 'chat-message-wrapper flex items-start space-x-4 mb-6';
        
        wrapper.innerHTML = `
            <div class="flex-shrink-0 mt-1">
                <img src="assets/images/logo.png" onerror="this.src='https://via.placeholder.com/32'" alt="Taskera AI" class="w-8 h-8 rounded-lg shadow-sm opacity-80">
            </div>
            <div class="flex items-center h-8">
                <div class="flex space-x-1.5 bg-zinc-900/50 px-3 py-2 rounded-xl border border-zinc-800">
                    <div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: 0s"></div>
                    <div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: 0.1s"></div>
                    <div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
                </div>
            </div>`;
        
        dom.chatLog.appendChild(wrapper);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const el = document.getElementById('typing-indicator');
        if (el) el.remove();
    }

    function scrollToBottom() {
        dom.chatLog.scrollTop = dom.chatLog.scrollHeight;
    }

    function formatAIResponse(text) {
        if (!text) return '';
        
        let formatted = escapeHtml(text);
        
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>');
        
        formatted = formatted.replace(/```([\s\S]*?)```/g, '<pre class="bg-zinc-900 p-3 rounded-lg my-2 overflow-x-auto"><code class="text-xs text-fuchsia-300">$1</code></pre>');
        
        formatted = formatted.replace(/`([^`]+)`/g, '<code class="bg-zinc-800 px-1.5 py-0.5 rounded text-fuchsia-300 font-mono text-xs">$1</code>');
        
        formatted = formatted.replace(/^\s*[-*]\s+(.*)$/gm, '<li class="ml-4 list-disc">$1</li>');
        
        formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" class="text-fuchsia-400 hover:text-fuchsia-300 underline">$1</a>');
        
        formatted = formatted.replace(/\n/g, '<br>');
        
        return formatted;
    }

    function escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function renderFileAttachments(names) {
        if (!names || !names.length) return '';
        
        return `
            <div class="mt-2 pt-2 border-t border-white/10 flex flex-wrap gap-2">
                ${names.map(name => `
                    <div class="flex items-center text-xs text-white/70 bg-black/20 px-2 py-1 rounded border border-white/5">
                        <svg class="w-3 h-3 mr-1 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.414a4 4 0 00-5.656-5.656l-6.415 6.415a6 6 0 108.486 8.486L20.5 13"></path>
                        </svg>
                        ${escapeHtml(name)}
                    </div>
                `).join('')}
            </div>
        `;
    }

    
    function handleFileStage(e) {
        const files = Array.from(e.target.files);
        if (!files.length) return;
        
        if (state.stagedFiles.length + files.length > MAX_FILES) {
            addSystemMessage(`Maximum ${MAX_FILES} files allowed.`);
            return;
        }
        
        files.forEach(file => {
            const sizeMB = file.size / (1024 * 1024);
            if (sizeMB > MAX_FILE_SIZE_MB) {
                addSystemMessage(`File "${file.name}" exceeds ${MAX_FILE_SIZE_MB}MB limit.`);
                return;
            }
            
            const fileId = generateUUID();
            state.stagedFiles.push({ id: fileId, file: file });
            renderFileChip(file, fileId);
        });
        
        e.target.value = ''; 
    }

    function renderFileChip(file, id) {
        const chip = document.createElement('div');
        chip.className = 'flex items-center bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 pr-1 text-xs text-zinc-300 animate-fade-in';
        chip.id = `file-chip-${id}`;
        
        let icon = `<svg class="w-3 h-3 mr-1.5 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path>
        </svg>`;
        
        if (file.type.startsWith('image/')) {
            const url = URL.createObjectURL(file);
            icon = `<img src="${url}" class="w-4 h-4 rounded object-cover mr-1.5">`;
        }

        chip.innerHTML = `
            ${icon}
            <span class="max-w-[100px] truncate mr-1">${escapeHtml(file.name)}</span>
            <button type="button" class="p-0.5 hover:bg-zinc-700 rounded-full text-zinc-500 hover:text-red-400 transition-colors" data-file-id="${id}">
                <svg class="w-3 h-3 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            </button>
        `;
        
        dom.filePreviewContainer.appendChild(chip);
    }

    function handleFileRemove(e) {
        const btn = e.target.closest('button');
        if (!btn || !btn.dataset.fileId) return;
        
        const fileId = btn.dataset.fileId;
        state.stagedFiles = state.stagedFiles.filter(f => f.id !== fileId);
        document.getElementById(`file-chip-${fileId}`).remove();
    }

    function clearStagedFiles() {
        state.stagedFiles = [];
        dom.filePreviewContainer.innerHTML = '';
    }

    
    async function handleAuthSubmit(e) {
        e.preventDefault();
        
        const email = dom.authEmail.value;
        const password = dom.authPassword.value;
        
        dom.authSubmitBtn.disabled = true;
        dom.authSubmitBtn.textContent = "Processing...";
        dom.authErrorMsg.classList.add('hidden');

        const endpoint = state.isLoginMode ? '/auth/login' : '/auth/signup';
        const payload = { email, password };

        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || "Authentication failed");
            }

            if (state.isLoginMode) {
                state.authToken = data.access_token;
                state.currentUserId = data.user_id;
                
                localStorage.setItem(KEYS.AUTH_TOKEN, state.authToken);
                localStorage.setItem(KEYS.USER_ID, state.currentUserId);
                localStorage.setItem(KEYS.USER_EMAIL, data.email);
                
                updateAuthUI(true, data.email);
                hideAuthModal();
                addSystemMessage("Successfully logged in!");
                
                if (dom.currentUserIdDisplay) {
                    dom.currentUserIdDisplay.textContent = state.currentUserId.substring(0, 20) + '...';
                }
            } else {
                state.isLoginMode = true;
                renderAuthModalState();
                
                dom.authErrorMsg.textContent = "Account created! Please sign in.";
                dom.authErrorMsg.classList.remove('hidden', 'text-red-400', 'bg-red-900/10');
                dom.authErrorMsg.classList.add('text-green-400', 'bg-green-900/10');
            }
            
        } catch (error) {
            console.error('Auth error:', error);
            dom.authErrorMsg.textContent = error.message;
            dom.authErrorMsg.classList.remove('hidden', 'text-green-400', 'bg-green-900/10');
            dom.authErrorMsg.classList.add('text-red-400', 'bg-red-900/10');
        } finally {
            dom.authSubmitBtn.disabled = false;
            dom.authSubmitBtn.textContent = state.isLoginMode ? "Sign In" : "Sign Up";
        }
    }

    function handleLogout() {
        localStorage.removeItem(KEYS.AUTH_TOKEN);
        localStorage.removeItem(KEYS.USER_ID);
        localStorage.removeItem(KEYS.USER_EMAIL);
        
        state.authToken = null;
        
        let guestId = 'guest_' + generateUUID();
        localStorage.setItem(KEYS.GUEST_ID, guestId);
        state.currentUserId = guestId;
        
        updateAuthUI(false);
        handleNewSession();
        addSystemMessage("Logged out successfully.");
        
        if (dom.currentUserIdDisplay) {
            dom.currentUserIdDisplay.textContent = guestId.substring(0, 20) + '...';
        }
    }

    function updateAuthUI(isLoggedIn, email = '') {
        if (isLoggedIn) {
            if(dom.guestAuthSection) dom.guestAuthSection.classList.add('hidden');
            if(dom.userProfileSection) dom.userProfileSection.classList.remove('hidden');
            if(dom.userEmailDisplay) dom.userEmailDisplay.textContent = email;
        } else {
            if(dom.guestAuthSection) dom.guestAuthSection.classList.remove('hidden');
            if(dom.userProfileSection) dom.userProfileSection.classList.add('hidden');
        }
    }

    function showAuthModal(isLogin = true, message = null) {
        state.isLoginMode = isLogin;
        renderAuthModalState();
        
        dom.authModal.classList.remove('hidden');
        setTimeout(() => {
            dom.authModal.classList.remove('opacity-0');
            dom.authModal.querySelector('.modal-content').classList.remove('scale-95', 'opacity-0');
        }, 10);
        
        if (message) {
            dom.authErrorMsg.textContent = message;
            dom.authErrorMsg.classList.remove('hidden');
            dom.authErrorMsg.classList.add('text-yellow-400', 'bg-yellow-900/10');
        }
    }

    function hideAuthModal() {
        dom.authModal.classList.add('opacity-0');
        dom.authModal.querySelector('.modal-content').classList.add('scale-95', 'opacity-0');
        
        setTimeout(() => {
            dom.authModal.classList.add('hidden');
            dom.authErrorMsg.classList.add('hidden');
        }, 300);
    }

    function toggleAuthMode(e) {
        e.preventDefault();
        state.isLoginMode = !state.isLoginMode;
        renderAuthModalState();
    }

    function renderAuthModalState() {
        if (state.isLoginMode) {
            dom.authModalTitle.textContent = "Sign In";
            dom.authSubmitBtn.textContent = "Sign In";
            dom.authSwitchText.textContent = "Don't have an account?";
            dom.authSwitchBtn.textContent = "Sign Up";
        } else {
            dom.authModalTitle.textContent = "Create Account";
            dom.authSubmitBtn.textContent = "Sign Up";
            dom.authSwitchText.textContent = "Already have an account?";
            dom.authSwitchBtn.textContent = "Sign In";
        }
        dom.authErrorMsg.classList.add('hidden');
    }

    
    async function handleNewSession() {
        const messages = dom.chatLog.querySelectorAll('.chat-message-wrapper');
        messages.forEach(msg => msg.remove());
        
        if(dom.welcomeScreen) dom.welcomeScreen.classList.remove('hidden');
        
        clearStagedFiles();
        dom.userInput.value = '';
        dom.userInput.focus();
        toggleSidebar(false);
    }

    function toggleSidebar(forceState) {
        if(!dom.sidebar) return;
        
        const isOpen = !dom.sidebar.classList.contains('-translate-x-full');
        const newState = (typeof forceState === 'boolean') ? forceState : !isOpen;
        
        if (newState) {
            dom.sidebar.classList.remove('-translate-x-full');
            dom.sidebarOverlay.classList.remove('hidden');
            dom.menuIcon.classList.add('hidden');
            dom.closeIcon.classList.remove('hidden');
        } else {
            dom.sidebar.classList.add('-translate-x-full');
            dom.sidebarOverlay.classList.add('hidden');
            dom.menuIcon.classList.remove('hidden');
            dom.closeIcon.classList.add('hidden');
        }
    }

    function setProcessing(isProcessing) {
        state.isProcessing = isProcessing;
        dom.userInput.disabled = isProcessing;
        dom.sendButton.disabled = isProcessing;
        dom.chatUploadBtn.disabled = isProcessing;
        
        if (!isProcessing) {
            dom.userInput.focus();
        }
    }

    function updateUIState() {
        if(!dom.chatLog) return;
        
        const hasMessages = dom.chatLog.querySelectorAll('.chat-message-wrapper').length > 0;
        
        if(dom.welcomeScreen) {
            if (hasMessages) {
                dom.welcomeScreen.classList.add('hidden');
            } else {
                dom.welcomeScreen.classList.remove('hidden');
            }
        }
    }

    
    async function fetchCsrfToken() {
        try {
            const response = await fetch(`${API_BASE_URL}/csrf-token`);
            if (response.ok) {
                const data = await response.json();
                state.csrfToken = data.csrf_token;
                console.log('✓ CSRF token fetched');
            }
        } catch (error) {
            console.error("CSRF Error:", error);
        }
    }

    
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    
    init();
});