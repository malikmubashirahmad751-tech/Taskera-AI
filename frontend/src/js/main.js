document.addEventListener('DOMContentLoaded', () => {
    
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    
    const API_BASE_URL = isLocal 
        ? 'http://127.0.0.1:7860' 
        : 'https://mubashir751-taskera-ai-backend.hf.space';
        
    const CHAT_ENDPOINT = '/api/chat';
    
    const KEYS = {
        AUTH_TOKEN: 'taskera_access_token',
        USER_ID: 'taskera_user_id',
        USER_EMAIL: 'taskera_user_email',
        GUEST_ID: 'taskera_guest_id'
    };

    const MAX_FILES = 10;
    const MAX_FILE_SIZE_MB = 10;
    const MAX_RETRY_ATTEMPTS = 3;
    const RETRY_DELAY_MS = 2000;

    let state = {
        currentUserId: null,
        authToken: null,
        stagedFiles: [],
        isLoginMode: true,
        isProcessing: false,
        retryCount: 0
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
        console.log(`Connecting to: ${API_BASE_URL}`);
        const googleBtn = document.querySelector('a[href*="/auth/google"]');
        if (googleBtn) {
        googleBtn.href = `${API_BASE_URL}/auth/google`; 
    }
        
        handleGoogleLoginRedirect();
        loadSession();
        setupEventListeners();
        setupSuggestionCards();
        updateUIState();
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
                
                window.history.replaceState({}, document.title, window.location.pathname);
                
                addSystemMessage("Successfully logged in with Google!");
            }
        } else if (urlParams.get('error') === 'auth_failed') {
            addSystemMessage("Authentication failed: " + (urlParams.get('details') || 'Unknown error'));
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
        } else {
            let guestId = localStorage.getItem(KEYS.GUEST_ID);
            if (!guestId) {
                guestId = 'guest_' + generateUUID();
                localStorage.setItem(KEYS.GUEST_ID, guestId);
            }
            state.currentUserId = guestId;
            updateAuthUI(false);
        }
        
        if (dom.currentUserIdDisplay) {
            dom.currentUserIdDisplay.textContent = state.currentUserId.substring(0, 10) + '...';
        }
    }

    function setupEventListeners() {
        if(dom.menuButton) dom.menuButton.addEventListener('click', () => toggleSidebar());
        if(dom.sidebarOverlay) dom.sidebarOverlay.addEventListener('click', () => toggleSidebar(false));
        
        if(dom.chatForm) dom.chatForm.addEventListener('submit', handleChatSubmit);
        if(dom.userInput) {
            dom.userInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (!state.isProcessing) handleChatSubmit(e);
                }
            });
        }
        
        if(dom.chatUploadBtn) dom.chatUploadBtn.addEventListener('click', () => {
            if (!state.isProcessing) dom.fileUploadInput.click();
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
        document.querySelectorAll('.suggestion-card').forEach(card => {
            card.addEventListener('click', () => {
                if (state.isProcessing) return;
                const textSpan = card.querySelector('span.text-zinc-200') || card.querySelector('h3') || card.querySelector('p');
                if (textSpan) {
                    dom.userInput.value = textSpan.textContent.trim();
                    dom.userInput.focus();
                }
            });
        });
    }

    async function handleChatSubmit(e) {
        if(e) e.preventDefault();
        
        if (state.isProcessing) return;
        
        const message = dom.userInput.value.trim();
        const hasFiles = state.stagedFiles.length > 0;
        
        if (!message && !hasFiles) return;
        
        state.retryCount = 0;
        
        await sendChatRequest(message, hasFiles);
    }

    async function sendChatRequest(message, hasFiles) {
        const fileNames = state.stagedFiles.map(f => f.file.name);
        addMessageToChat('user', message, hasFiles ? fileNames : null);
        
        if(dom.welcomeScreen) dom.welcomeScreen.classList.add('hidden');

        const formData = new FormData();
        formData.append('query', message);
        formData.append('user_id', state.currentUserId);
        
        const userEmail = localStorage.getItem(KEYS.USER_EMAIL);
        if (userEmail) formData.append('email', userEmail);
        
        state.stagedFiles.forEach(f => formData.append('files', f.file));

        dom.userInput.value = '';
        clearStagedFiles();
        setProcessing(true);
        addTypingIndicator();

        try {
            const headers = {};
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
                showAuthModal(false, "Create an account to continue using Taskera AI");
                return;
            }
            
            if (response.status === 401) {
                handleLogout();
                showAuthModal(true, "Session expired. Please log in again.");
                return;
            }

            if (response.status === 429) {
                addSystemMessage("Rate limit exceeded. Please wait a moment before trying again.");
                await new Promise(resolve => setTimeout(resolve, 3000));
                return;
            }

            if (response.status === 504 || response.status === 503) {
                if (state.retryCount < MAX_RETRY_ATTEMPTS) {
                    state.retryCount++;
                    addSystemMessage(`Request timeout. Retrying (${state.retryCount}/${MAX_RETRY_ATTEMPTS})...`);
                    await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS * state.retryCount));
                    return await sendChatRequest(message, hasFiles);
                } else {
                    addSystemMessage("Service temporarily unavailable. Please try again in a few minutes.");
                    state.retryCount = 0;
                    return;
                }
            }

            const data = await response.json();
            
            if (!response.ok) {
                const errorMsg = data.detail?.message || data.detail || data.error || `Error: ${response.status}`;
                throw new Error(errorMsg);
            }

            let aiResponse = data.answer || JSON.stringify(data, null, 2);
            if (Array.isArray(aiResponse)) aiResponse = aiResponse.join('\n');
            
            addMessageToChat('ai', aiResponse);
            state.retryCount = 0; 

        } catch (error) {
            removeTypingIndicator();
            console.error('Chat error:', error);
            
            if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
                if (state.retryCount < MAX_RETRY_ATTEMPTS) {
                    state.retryCount++;
                    addSystemMessage(`Connection error. Retrying (${state.retryCount}/${MAX_RETRY_ATTEMPTS})...`);
                    await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS * state.retryCount));
                    return await sendChatRequest(message, hasFiles);
                } else {
                    addSystemMessage("Cannot connect to server. Please check your internet connection.");
                    state.retryCount = 0;
                }
            } else {
                addSystemMessage(`Error: ${error.message}`);
            }
        } finally {
            setProcessing(false);
        }
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
            if (!response.ok) throw new Error(data.detail || data.message || "Authentication failed");

            if (state.isLoginMode) {
                state.authToken = data.access_token;
                state.currentUserId = data.user_id;
                
                localStorage.setItem(KEYS.AUTH_TOKEN, state.authToken);
                localStorage.setItem(KEYS.USER_ID, state.currentUserId);
                localStorage.setItem(KEYS.USER_EMAIL, data.email);
                
                updateAuthUI(true, data.email);
                hideAuthModal();
                addSystemMessage(" Successfully logged in!");
            } else {
                state.isLoginMode = true;
                renderAuthModalState();
                dom.authErrorMsg.textContent = "Account created! Please sign in.";
                dom.authErrorMsg.classList.remove('hidden', 'text-red-400', 'bg-red-900/10');
                dom.authErrorMsg.classList.add('text-green-400', 'bg-green-900/10');
            }
        } catch (error) {
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
                        <img src="assets/images/logo.png" onerror="this.src='https://via.placeholder.com/32'" alt="Taskera" class="w-8 h-8 rounded-lg shadow-sm">
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
                <img src="assets/images/logo.png" onerror="this.src='https://via.placeholder.com/32'" class="w-8 h-8 rounded-lg shadow-sm opacity-80">
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
            const content = dom.authModal.querySelector('.modal-content') || dom.authModal.children[0];
            if(content) content.classList.remove('scale-95', 'opacity-0');
        }, 10);
        
        if (message) {
            dom.authErrorMsg.textContent = message;
            dom.authErrorMsg.classList.remove('hidden');
        }
    }

    function hideAuthModal() {
        dom.authModal.classList.add('opacity-0');
        const content = dom.authModal.querySelector('.modal-content') || dom.authModal.children[0];
        if(content) content.classList.add('scale-95', 'opacity-0');
        
        setTimeout(() => {
            dom.authModal.classList.add('hidden');
            dom.authErrorMsg.classList.add('hidden');
        }, 300);
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

    function toggleAuthMode(e) {
        e.preventDefault();
        state.isLoginMode = !state.isLoginMode;
        renderAuthModalState();
    }

    function toggleSidebar(forceState) {
        if(!dom.sidebar) return;
        const isOpen = !dom.sidebar.classList.contains('-translate-x-full');
        const newState = (typeof forceState === 'boolean') ? forceState : !isOpen;
        if (newState) {
            dom.sidebar.classList.remove('-translate-x-full');
            dom.sidebarOverlay.classList.remove('hidden');
            if(dom.menuIcon) dom.menuIcon.classList.add('hidden');
            if(dom.closeIcon) dom.closeIcon.classList.remove('hidden');
        } else {
            dom.sidebar.classList.add('-translate-x-full');
            dom.sidebarOverlay.classList.add('hidden');
            if(dom.menuIcon) dom.menuIcon.classList.remove('hidden');
            if(dom.closeIcon) dom.closeIcon.classList.add('hidden');
        }
    }

    function handleNewSession() {
        dom.chatLog.querySelectorAll('.chat-message-wrapper').forEach(msg => msg.remove());
        if(dom.welcomeScreen) dom.welcomeScreen.classList.remove('hidden');
        clearStagedFiles();
        dom.userInput.value = '';
        dom.userInput.focus();
        toggleSidebar(false);
        state.retryCount = 0;
    }

    function setProcessing(isProcessing) {
        state.isProcessing = isProcessing;
        dom.userInput.disabled = isProcessing;
        dom.sendButton.disabled = isProcessing;
        dom.chatUploadBtn.disabled = isProcessing;
        if (!isProcessing) dom.userInput.focus();
    }

    function updateUIState() {
        const hasMessages = dom.chatLog.querySelectorAll('.chat-message-wrapper').length > 0;
        if(dom.welcomeScreen) {
            hasMessages ? dom.welcomeScreen.classList.add('hidden') : dom.welcomeScreen.classList.remove('hidden');
        }
    }

    function formatAIResponse(text) {
        if (!text) return '';
        let formatted = escapeHtml(text);
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>');
        formatted = formatted.replace(/```([\s\S]*?)```/g, '<pre class="bg-zinc-900 p-3 rounded-lg my-2 overflow-x-auto"><code class="text-xs text-fuchsia-300">$1</code></pre>');
        formatted = formatted.replace(/`([^`]+)`/g, '<code class="bg-zinc-800 px-1.5 py-0.5 rounded text-fuchsia-300 font-mono text-xs">$1</code>');
        formatted = formatted.replace(/^\s*[-*]\s+(.*)$/gm, '<li class="ml-4 list-disc">$1</li>');
        formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" class="text-fuchsia-400 hover:text-fuchsia-300 underline">$1</a>');
        return formatted.replace(/\n/g, '<br>');
    }

    function escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    function renderFileAttachments(names) {
        if (!names || !names.length) return '';
        return `<div class="mt-2 pt-2 border-t border-white/10 flex flex-wrap gap-2">${names.map(name => `<div class="flex items-center text-xs text-white/70 bg-black/20 px-2 py-1 rounded border border-white/5">${escapeHtml(name)}</div>`).join('')}</div>`;
    }

    function handleFileStage(e) {
        const files = Array.from(e.target.files);
        if (state.stagedFiles.length + files.length > MAX_FILES) return addSystemMessage(`Maximum ${MAX_FILES} files allowed`);
        files.forEach(file => {
            if (file.size / (1024 * 1024) > MAX_FILE_SIZE_MB) return addSystemMessage(`${file.name} exceeds ${MAX_FILE_SIZE_MB}MB limit`);
            const id = generateUUID();
            state.stagedFiles.push({ id, file });
            renderFileChip(file, id);
        });
        e.target.value = '';
    }

    function renderFileChip(file, id) {
        const chip = document.createElement('div');
        chip.className = 'flex items-center bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 pr-1 text-xs text-zinc-300 animate-fade-in';
        chip.id = `file-chip-${id}`;
        chip.innerHTML = `<span class="max-w-[100px] truncate mr-1">${escapeHtml(file.name)}</span><button type="button" class="p-0.5 hover:text-red-400" data-file-id="${id}">✕</button>`;
        dom.filePreviewContainer.appendChild(chip);
    }

    function handleFileRemove(e) {
        const btn = e.target.closest('button');
        if (!btn || !btn.dataset.fileId) return;
        const id = btn.dataset.fileId;
        state.stagedFiles = state.stagedFiles.filter(f => f.id !== id);
        document.getElementById(`file-chip-${id}`).remove();
    }

    function clearStagedFiles() {
        state.stagedFiles = [];
        dom.filePreviewContainer.innerHTML = '';
    }

    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }

    init();
});