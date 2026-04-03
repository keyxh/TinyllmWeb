const API_BASE = '/api';

function showMessage(text, type = 'info') {
    const messageEl = document.getElementById('message');
    messageEl.textContent = text;
    messageEl.className = `message ${type}`;
    messageEl.style.display = 'block';
    
    setTimeout(() => {
        messageEl.style.display = 'none';
    }, 3000);
}

function switchTab(tab) {
    const tabs = document.querySelectorAll('.tab-btn');
    const forms = document.querySelectorAll('.form-container');
    
    tabs.forEach(t => t.classList.remove('active'));
    forms.forEach(f => f.classList.remove('active'));
    
    if (tab === 'login') {
        tabs[0].classList.add('active');
        document.getElementById('login-form').classList.add('active');
    } else {
        tabs[1].classList.add('active');
        document.getElementById('code-form').classList.add('active');
    }
}

async function handleLogin(event) {
    event.preventDefault();
    
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    
    try {
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email, password })
        });
        
        const result = await response.json();
        
        if (result.success) {
            localStorage.setItem('token', result.data.access_token);
            localStorage.setItem('user', JSON.stringify(result.data.user));
            showMessage('登录成功，正在跳转...', 'success');
            setTimeout(() => {
                window.location.href = '/app';
            }, 1000);
        } else {
            showMessage(result.message || '登录失败', 'error');
        }
    } catch (error) {
        showMessage('网络错误，请稍后重试', 'error');
        console.error('Login error:', error);
    }
}

async function sendVerificationCode() {
    const email = document.getElementById('code-email').value;
    
    if (!email) {
        showMessage('请输入邮箱', 'error');
        return;
    }
    
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
        showMessage('邮箱格式不正确', 'error');
        return;
    }
    
    const btn = document.getElementById('send-code-btn');
    btn.disabled = true;
    btn.textContent = '发送中...';
    
    try {
        const response = await fetch(`${API_BASE}/auth/send-verification-code`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showMessage('验证码已发送', 'success');
            let countdown = 60;
            btn.disabled = true;
            
            const timer = setInterval(() => {
                countdown--;
                btn.textContent = `${countdown}秒后重发`;
                
                if (countdown <= 0) {
                    clearInterval(timer);
                    btn.disabled = false;
                    btn.textContent = '发送验证码';
                }
            }, 1000);
        } else {
            showMessage(result.message || '发送失败', 'error');
            btn.disabled = false;
            btn.textContent = '发送验证码';
        }
    } catch (error) {
        showMessage('网络错误，请稍后重试', 'error');
        console.error('Send code error:', error);
        btn.disabled = false;
        btn.textContent = '发送验证码';
    }
}

async function handleCodeLogin(event) {
    event.preventDefault();
    
    const email = document.getElementById('code-email').value;
    const code = document.getElementById('verification-code').value;
    
    if (!email) {
        showMessage('请输入邮箱', 'error');
        return;
    }
    
    if (!code || code.length !== 6) {
        showMessage('请输入6位验证码', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/auth/verify-code-login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email, code })
        });
        
        const result = await response.json();
        
        if (result.success) {
            localStorage.setItem('token', result.data.access_token);
            localStorage.setItem('user', JSON.stringify(result.data.user));
            showMessage('登录成功，正在跳转...', 'success');
            setTimeout(() => {
                window.location.href = '/app';
            }, 1000);
        } else {
            showMessage(result.message || '登录失败', 'error');
        }
    } catch (error) {
        showMessage('网络错误，请稍后重试', 'error');
        console.error('Code login error:', error);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('token');
    if (token) {
        window.location.href = '/app';
    }
});
