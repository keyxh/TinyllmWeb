const { createApp, ref, onMounted } = Vue;
const { ElMessage } = ElementPlus;

const app = createApp({
    setup() {
        const user = ref({});
        
        const token = localStorage.getItem('token');
        
        async function loadUserInfo() {
            const savedUser = localStorage.getItem('user');
            if (savedUser) {
                user.value = JSON.parse(savedUser);
            }
        }
        
        function handleCommand(command) {
            if (command === 'logout') {
                localStorage.removeItem('token');
                localStorage.removeItem('user');
                window.location.href = '/';
            } else if (command === 'home') {
                window.location.href = '/app';
            } else if (command === 'profile') {
                ElMessage.info('请在首页修改个人资料');
                window.location.href = '/app';
            }
        }
        
        function copyText(text) {
            navigator.clipboard.writeText(text).then(() => {
                ElMessage.success('已复制到剪贴板');
            }).catch(() => {
                ElMessage.error('复制失败');
            });
        }
        
        onMounted(() => {
            if (!token) {
                window.location.href = '/';
                return;
            }
            loadUserInfo();
        });
        
        return {
            user,
            handleCommand,
            copyText
        };
    }
});

app.use(ElementPlus);
app.mount('#app');
