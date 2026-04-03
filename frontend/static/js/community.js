const { createApp, ref, onMounted } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

const API_BASE = '/api';

const app = createApp({
    setup() {
        const user = ref({});
        const posts = ref([]);
        const showCreateDialog = ref(false);
        const creating = ref(false);
        
        const postForm = ref({
            title: '',
            content: '',
            app_url: '',
            api_url: ''
        });
        
        const uploadedImages = ref([]);
        const token = localStorage.getItem('token');
        
        const uploadUrl = `${API_BASE}/community/upload/image`;
        const uploadHeaders = ref({});
        
        async function apiRequest(url, options = {}) {
            const headers = {
                'Content-Type': 'application/json',
                ...options.headers
            };
            
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            
            try {
                const response = await fetch(url, { ...options, headers });
                
                if (response.status === 401) {
                    localStorage.removeItem('token');
                    localStorage.removeItem('user');
                    window.location.href = '/';
                    return null;
                }
                
                const data = await response.json();
                return data;
            } catch (error) {
                console.error('API Error:', error);
                return { success: false, message: error.message };
            }
        }
        
        async function loadUserInfo() {
            const savedUser = localStorage.getItem('user');
            if (savedUser) {
                user.value = JSON.parse(savedUser);
            }
            if (token) {
                uploadHeaders.value = {
                    'Authorization': `Bearer ${token}`
                };
            }
        }
        
        async function loadPosts() {
            const result = await apiRequest(`${API_BASE}/community/posts`);
            if (result && result.success) {
                posts.value = result.data.map(post => {
                    if (post.images) {
                        post.images_list = post.images.split(',').filter(img => img.trim());
                    } else {
                        post.images_list = [];
                    }
                    return post;
                });
            }
        }
        
        function handleUploadSuccess(response, file, fileList) {
            if (response.success) {
                uploadedImages.value.push({
                    name: response.data.filename,
                    url: response.data.url
                });
                ElMessage.success('图片上传成功');
            } else {
                ElMessage.error(response.message || '图片上传失败');
            }
        }
        
        function handleUploadRemove(file, fileList) {
            const index = uploadedImages.value.findIndex(img => img.name === file.name || img.url === file.url);
            if (index > -1) {
                uploadedImages.value.splice(index, 1);
            }
        }
        
        function handleUploadError(err, file, fileList) {
            ElMessage.error('图片上传失败');
            console.error('Upload error:', err);
        }
        
        async function createPost() {
            if (!postForm.value.title) {
                ElMessage.error('标题不能为空');
                return;
            }
            
            if (!postForm.value.content) {
                ElMessage.error('内容不能为空');
                return;
            }
            
            creating.value = true;
            
            const images = uploadedImages.value.map(img => img.url).join(',');
            
            const result = await apiRequest(`${API_BASE}/community/posts`, {
                method: 'POST',
                body: JSON.stringify({
                    title: postForm.value.title,
                    content: postForm.value.content,
                    app_url: postForm.value.app_url,
                    api_url: postForm.value.api_url,
                    images: images
                })
            });
            creating.value = false;
            
            if (result && result.success) {
                ElMessage.success('发布成功');
                showCreateDialog.value = false;
                postForm.value = { title: '', content: '', app_url: '', api_url: '' };
                uploadedImages.value = [];
                loadPosts();
            } else {
                ElMessage.error(result.message || '发布失败');
            }
        }
        
        async function deletePost(post) {
            try {
                await ElMessageBox.confirm('确定要删除这条分享吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const result = await apiRequest(`${API_BASE}/community/posts/${post.id}`, {
                    method: 'DELETE'
                });
                
                if (result && result.success) {
                    ElMessage.success('删除成功');
                    loadPosts();
                } else {
                    ElMessage.error(result.message || '删除失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    ElMessage.error('删除失败');
                }
            }
        }
        
        function handlePostCommand(command, post) {
            if (command === 'delete') {
                deletePost(post);
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
        
        function formatDate(dateStr) {
            const date = new Date(dateStr);
            return date.toLocaleString('zh-CN');
        }
        
        onMounted(() => {
            if (!token) {
                window.location.href = '/';
                return;
            }
            loadUserInfo();
            loadPosts();
        });
        
        return {
            user,
            posts,
            showCreateDialog,
            creating,
            postForm,
            uploadedImages,
            uploadUrl,
            uploadHeaders,
            createPost,
            handleUploadSuccess,
            handleUploadRemove,
            handleUploadError,
            handlePostCommand,
            handleCommand,
            formatDate
        };
    }
});

app.use(ElementPlus);
app.mount('#app');
