        const { createApp, ref, computed, onMounted, nextTick, watch } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

const API_BASE = '/api';

const app = createApp({
    setup() {
        const user = ref({});
        const activeMenu = ref('dashboard');
        const datasets = ref([]);
        const tasks = ref([]);
        const models = ref([]);
        const deployments = ref([]);
        const baseModels = ref([]);
        const stats = ref({ datasets: 0, models: 0, deployments: 0 });
        
        const showUploadDialog = ref(false);
        const showCreateTaskDialog = ref(false);
        const showTestDialog = ref(false);
        const uploadFile = ref(null);
        const uploading = ref(false);
        const creating = ref(false);
        const deploying = ref(false);
        
        const taskForm = ref({
            model_name: '',
            base_model: '',
            dataset_id: null,
            num_epochs: 5
        });
        
        const testDeployment = ref({ model_name: '', api_url: '', model_id: 0 });
        const testMessages = ref([]);
        const testInput = ref('');
        const testStreaming = ref(false);
        const testCurrentContent = ref('');
        const testMessagesRef = ref(null);
        
        const showLogDialog = ref(false);
        const showDeployDialog = ref(false);
        const showProfileDialog = ref(false);
        const currentModel = ref({ model_name: '' });
        const logs = ref([]);
        const logMessagesRef = ref(null);
        const deployForm = ref({
            model_id: 0,
            hours: 24,
            cost: '未知',
            totalCost: 0
        });
        const profileForm = ref({
            username: '',
            email: ''
        });
        const updatingProfile = ref(false);
        const communityPosts = ref([]);
        const showCommunityCreateDialog = ref(false);
        const communityPostForm = ref({
            title: '',
            content: '',
            link: ''
        });
        const creatingCommunityPost = ref(false);
        const showTrainingLogDialog = ref(false);
        const trainingLogTask = ref({
            id: 0,
            model_name: '',
            base_model: '',
            status: '',
            progress: 0,
            logs: ''
        });
        const trainingLogContent = ref('');
        const loadingTrainingLog = ref(false);
        const trainingLogRef = ref(null);
        
        const showRenewDialog = ref(false);
        const renewDeployment = ref(null);
        const renewForm = ref({
            hours: 24,
            cost: '未知'
        });
        const renewing = ref(false);
        
        const showRechargeDialog = ref(false);
        const rechargeForm = ref({
            points: 10
        });
        const rechargeAmount = ref(1.00);
        const currentOrder = ref(null);
        const creatingRechargeOrder = ref(false);
        const checkingPayment = ref(false);
        const countdown = ref('00:00');
        const countdownTimer = ref(null);
        const qrCodeUrl = ref('/backend/static/wx.png');
        
        const token = localStorage.getItem('token');
        
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
            const result = await apiRequest(`${API_BASE}/user/info`);
            if (result && result.success) {
                user.value = result.data;
                const savedUser = localStorage.getItem('user');
                if (!savedUser) {
                    localStorage.setItem('user', JSON.stringify(result.data));
                }
            }
        }
        
        async function loadDatasets() {
            const result = await apiRequest(`${API_BASE}/datasets/`);
            console.log('Datasets API result:', result);
            if (result && result.success) {
                datasets.value = result.data;
                stats.value.datasets = result.data.length;
                console.log('Datasets loaded:', datasets.value);
            } else {
                console.error('Failed to load datasets:', result);
            }
        }
        
        async function loadTasks() {
            const result = await apiRequest(`${API_BASE}/training/tasks`);
            if (result && result.success) {
                tasks.value = result.data;
            }
        }
        
        async function loadModels() {
            const result = await apiRequest(`${API_BASE}/models/`);
            console.log('Models API result:', result);
            if (result && result.success) {
                models.value = result.data;
                stats.value.models = result.data.length;
                console.log('Models loaded:', models.value);
                await loadDeployments();
            }
        }
        
        async function loadDeployments() {
            const result = await apiRequest(`${API_BASE}/deployments/`);
            if (result && result.success) {
                deployments.value = result.data;
                stats.value.deployments = result.data.filter(d => d.status === 'active').length;
            }
        }
        
        async function loadBaseModels() {
            const result = await apiRequest(`${API_BASE}/training/base-models`);
            console.log('[DEBUG] 基础模型数据:', result);
            if (result && result.success) {
                baseModels.value = result.data;
                console.log('[DEBUG] baseModels 已加载:', baseModels.value);
            }
        }
        
        function handleFileChange(file) {
            uploadFile.value = file.raw;
        }
        
        async function uploadDataset() {
            if (!uploadFile.value) {
                ElMessage.warning('请选择文件');
                return;
            }
            
            uploading.value = true;
            const formData = new FormData();
            formData.append('file', uploadFile.value);
            
            try {
                const response = await fetch(`${API_BASE}/datasets/upload`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    ElMessage.success('上传成功');
                    showUploadDialog.value = false;
                    uploadFile.value = null;
                    await loadDatasets();
                } else {
                    ElMessage.error(result.message || '上传失败');
                }
            } catch (error) {
                ElMessage.error('上传失败');
                console.error(error);
            } finally {
                uploading.value = false;
            }
        }
        
        async function deleteDataset(id) {
            try {
                await ElMessageBox.confirm('确定要删除这个数据集吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const result = await apiRequest(`${API_BASE}/datasets/${id}`, { method: 'DELETE' });
                
                if (result && result.success) {
                    ElMessage.success('删除成功');
                    await loadDatasets();
                } else {
                    ElMessage.error(result.message || '删除失败');
                }
            } catch (error) {
                if (error !== 'cancel') ElMessage.error('删除失败');
            }
        }
        
        async function createTask() {
            if (!taskForm.value.model_name || !taskForm.value.base_model || !taskForm.value.dataset_id) {
                ElMessage.warning('请填写完整信息');
                return;
            }
            
            creating.value = true;
            
            console.log('Creating task with data:', taskForm.value);
            
            const result = await apiRequest(`${API_BASE}/training/create`, {
                method: 'POST',
                body: JSON.stringify(taskForm.value)
            });
            
            console.log('Create task result:', result);
            
            if (result && result.success) {
                ElMessage.success('任务创建成功');
                showCreateTaskDialog.value = false;
                taskForm.value = { 
                    model_name: '', 
                    base_model: '', 
                    dataset_id: null, 
                    num_epochs: 5
                };
                await loadUserInfo();
                await loadTasks();
            } else {
                let errorMsg = result.message || '创建失败';
                if (result.errors && result.errors.length > 0) {
                    errorMsg = result.errors[0].msg || errorMsg;
                }
                ElMessage.error(errorMsg);
            }
            
            creating.value = false;
        }
        
        async function cancelTask(id) {
            try {
                await ElMessageBox.confirm('确定要取消这个任务吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const result = await apiRequest(`${API_BASE}/training/tasks/${id}/cancel`, { method: 'POST' });
                
                if (result && result.success) {
                    ElMessage.success('取消成功');
                    await loadUserInfo();
                    await loadTasks();
                } else {
                    ElMessage.error(result.message || '取消失败');
                }
            } catch (error) {
                if (error !== 'cancel') ElMessage.error('取消失败');
            }
        }
        
        async function restartTask(id) {
            try {
                const task = tasks.value.find(t => t.id === id);
                let cost = 30;
                if (task && task.base_model) {
                    const baseModelsResult = await apiRequest(`${API_BASE}/training/base-models`);
                    if (baseModelsResult && baseModelsResult.success) {
                        const baseModelsList = baseModelsResult.data;
                        for (const bm of baseModelsList) {
                            if (bm.name === task.base_model) {
                                cost = bm.training_cost?.min || 30;
                                break;
                            }
                        }
                    }
                }
                
                await ElMessageBox.confirm(`确定要重新开始训练吗？这将消耗${cost}积分。`, '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const result = await apiRequest(`${API_BASE}/training/tasks/${id}/restart`, { method: 'POST' });
                
                if (result && result.success) {
                    ElMessage.success('重新训练任务已创建');
                    await loadUserInfo();
                    await loadTasks();
                } else {
                    ElMessage.error(result.message || '重启失败');
                }
            } catch (error) {
                if (error !== 'cancel') ElMessage.error('重启失败');
            }
        }
        
        async function deleteTask(id) {
            try {
                await ElMessageBox.confirm('确定要删除这个训练任务吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const result = await apiRequest(`${API_BASE}/training/tasks/${id}`, { method: 'DELETE' });
                
                if (result && result.success) {
                    ElMessage.success('删除成功');
                    await loadTasks();
                    await loadModels();
                } else {
                    ElMessage.error(result.message || '删除失败');
                }
            } catch (error) {
                if (error !== 'cancel') ElMessage.error('删除失败');
            }
        }
        
        async function viewTrainingLog(task) {
            trainingLogTask.value = task;
            trainingLogContent.value = '';
            showTrainingLogDialog.value = true;
            await loadTrainingLog();
        }
        
        async function loadTrainingLog() {
            if (!trainingLogTask.value.id) return;
            
            loadingTrainingLog.value = true;
            try {
                const result = await apiRequest(`${API_BASE}/training/tasks/${trainingLogTask.value.id}`);
                
                if (result && result.success) {
                    trainingLogContent.value = result.data.logs || '暂无日志';
                    trainingLogTask.value = result.data;
                    
                    await nextTick();
                    if (trainingLogRef.value) {
                        trainingLogRef.value.scrollTop = trainingLogRef.value.scrollHeight;
                    }
                }
            } catch (error) {
                console.error('加载日志失败:', error);
                trainingLogContent.value = '加载日志失败';
            }
            loadingTrainingLog.value = false;
        }
        
        async function deleteModel(id) {
            try {
                await ElMessageBox.confirm('确定要删除这个模型吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const result = await apiRequest(`${API_BASE}/models/${id}`, { method: 'DELETE' });
                
                if (result && result.success) {
                    ElMessage.success('删除成功');
                    await loadModels();
                } else {
                    ElMessage.error(result.message || '删除失败');
                }
            } catch (error) {
                if (error !== 'cancel') ElMessage.error('删除失败');
            }
        }
        
        async function deployModel(modelId) {
            console.log('[DEBUG] deployModel 被调用，modelId:', modelId);
            
            const model = models.value.find(m => m.id === modelId);
            if (!model) {
                console.error('[DEBUG] 模型不存在，modelId:', modelId);
                ElMessage.error('模型不存在');
                return;
            }
            
            console.log('[DEBUG] 找到模型:', model);
            
            deployForm.value.model_id = modelId;
            deployForm.value.hours = 24;
            deployForm.value.cost = '计算中...';
            deployForm.value.totalCost = 0;
            
            console.log('[DEBUG] 打开部署对话框');
            showDeployDialog.value = true;
            
            console.log('[DEBUG] 开始计算部署费用...');
            try {
                const result = await apiRequest(`${API_BASE}/deployments/calculate?model_id=${modelId}`, {
                    method: 'GET'
                });
                
                console.log('部署费用计算结果:', result);
                
                if (result && result.success && typeof result.data?.cost === 'number') {
                    deployForm.value.cost = result.data.cost;
                    deployForm.value.totalCost = result.data.cost;
                    console.log('[DEBUG] 部署费用计算成功:', result.data.cost);
                } else {
                    deployForm.value.cost = '未知';
                    deployForm.value.totalCost = 0;
                    console.error('部署费用计算失败:', result);
                }
            } catch (error) {
                console.error('部署费用计算异常:', error);
                deployForm.value.cost = '计算失败';
                deployForm.value.totalCost = 0;
            }
        }
        
        watch(() => deployForm.value.hours, (newHours, oldHours) => {
            if (typeof deployForm.value.cost === 'number' && deployForm.value.cost > 0) {
                const oldTotal = deployForm.value.totalCost;
                deployForm.value.totalCost = Math.ceil(deployForm.value.cost * (newHours / 24));
                console.log(`[DEBUG] 部署时长变更: ${oldHours} -> ${newHours}小时, 总费用: ${oldTotal} -> ${deployForm.value.totalCost}`);
            }
        });
        
        watch(() => deployForm.value.cost, (newCost, oldCost) => {
            if (typeof newCost === 'number' && newCost > 0) {
                const oldTotal = deployForm.value.totalCost;
                deployForm.value.totalCost = Math.ceil(newCost * (deployForm.value.hours / 24));
                console.log(`[DEBUG] 部署单价变更: ${oldCost} -> ${newCost}积分/天, 总费用: ${oldTotal} -> ${deployForm.value.totalCost}`);
            }
        });
        
        async function confirmDeploy() {
            deploying.value = true;
            
            const result = await apiRequest(`${API_BASE}/deployments/create?model_id=${deployForm.value.model_id}&hours=${deployForm.value.hours}`, {
                method: 'POST'
            });
            
            if (result && result.success) {
                ElMessage.success(`部署成功！API: ${result.data.api_url}`);
                showDeployDialog.value = false;
                await loadUserInfo();
                await loadDeployments();
            } else {
                ElMessage.error(result.message || '部署失败');
            }
            
            deploying.value = false;
        }
        
        async function stopDeployment(id) {
            try {
                await ElMessageBox.confirm('确定要停止这个部署吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const result = await apiRequest(`${API_BASE}/deployments/${id}/stop`, { method: 'POST' });
                
                if (result && result.success) {
                    ElMessage.success('停止成功');
                    await loadDeployments();
                    await loadModels();
                } else {
                    ElMessage.error(result.message || '停止失败');
                }
            } catch (error) {
                if (error !== 'cancel') ElMessage.error('停止失败');
            }
        }
        
        async function openRenewDialog(deployment) {
            console.log('[DEBUG] openRenewDialog 被调用，deployment:', deployment);
            
            renewDeployment.value = deployment;
            renewForm.value.hours = 24;
            renewForm.value.cost = '计算中...';
            
            showRenewDialog.value = true;
            
            await calculateRenewCost();
        }
        
        async function calculateRenewCost() {
            if (!renewDeployment.value) return;
            
            try {
                const modelId = renewDeployment.value.model_id;
                const result = await apiRequest(`${API_BASE}/deployments/calculate?model_id=${modelId}`, {
                    method: 'GET'
                });
                
                console.log('续期费用计算结果:', result);
                
                if (result && result.success && typeof result.data?.cost === 'number') {
                    const dailyCost = result.data.cost;
                    const hours = renewForm.value.hours;
                    renewForm.value.cost = Math.ceil(dailyCost * (hours / 24));
                    console.log('[DEBUG] 续期费用计算成功:', renewForm.value.cost, '积分');
                } else {
                    renewForm.value.cost = '未知';
                    console.error('续期费用计算失败:', result);
                }
            } catch (error) {
                console.error('续期费用计算异常:', error);
                renewForm.value.cost = '计算失败';
            }
        }
        
        async function confirmRenew() {
            if (!renewDeployment.value) return;
            
            renewing.value = true;
            
            try {
                const deploymentId = renewDeployment.value.deployment_id;
                const result = await apiRequest(`${API_BASE}/deployments/${deploymentId}/extend?hours=${renewForm.value.hours}`, {
                    method: 'POST'
                });
                
                if (result && result.success) {
                    ElMessage.success(`续期成功！新到期时间: ${formatDateTime(result.data.new_expires_at)}`);
                    showRenewDialog.value = false;
                    await loadDeployments();
                    await loadModels();
                } else {
                    ElMessage.error(result.message || '续期失败');
                }
            } catch (error) {
                console.error('续期异常:', error);
                ElMessage.error('续期失败');
            } finally {
                renewing.value = false;
            }
        }
        
        function formatDateTime(dateStr) {
            if (!dateStr) return '-';
            try {
                const date = new Date(dateStr);
                return date.toLocaleString('zh-CN', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (e) {
                return dateStr;
            }
        }
        
        function copyApiUrl(url) {
            navigator.clipboard.writeText(url).then(() => {
                ElMessage.success('已复制');
            }).catch(() => {
                ElMessage.error('复制失败');
            });
        }
        
        function copyApiKey(key) {
            navigator.clipboard.writeText(key).then(() => {
                ElMessage.success('已复制');
            }).catch(() => {
                ElMessage.error('复制失败');
            });
        }
        
        async function loadCommunityPosts() {
            const result = await apiRequest(`${API_BASE}/community/posts`);
            if (result && result.success) {
                communityPosts.value = result.data;
            }
        }
        
        async function createCommunityPost() {
            if (!communityPostForm.value.title) {
                ElMessage.error('标题不能为空');
                return;
            }
            
            if (!communityPostForm.value.content) {
                ElMessage.error('内容不能为空');
                return;
            }
            
            creatingCommunityPost.value = true;
            const result = await apiRequest(`${API_BASE}/community/posts`, {
                method: 'POST',
                body: JSON.stringify(communityPostForm.value)
            });
            creatingCommunityPost.value = false;
            
            if (result && result.success) {
                ElMessage.success('发布成功');
                showCommunityCreateDialog.value = false;
                communityPostForm.value = { title: '', content: '', link: '' };
                loadCommunityPosts();
            } else {
                ElMessage.error(result.message || '发布失败');
            }
        }
        
        async function deleteCommunityPost(post) {
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
                    loadCommunityPosts();
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
                deleteCommunityPost(post);
            }
        }
        
        const isModelDeployed = computed(() => (modelId) => {
            return deployments.value.some(d => d.model_id === modelId && d.status === 'active');
        });

        const modelsWithDeployment = computed(() => {
            return models.value.map(model => {
                const deployment = deployments.value.find(d => d.model_id === model.id && d.status === 'active');
                return {
                    ...model,
                    model_id: model.id,
                    deployment_status: !!deployment,
                    deployment_id: deployment?.id,
                    api_url: deployment?.api_url,
                    api_key: deployment?.api_key,
                    device_name: deployment?.device_name,
                    expires_at: deployment?.expires_at
                };
            });
        });
        
        async function stopDeploymentByModel(modelId) {
            const deployment = deployments.value.find(d => d.model_id === modelId && d.status === 'active');
            if (deployment) {
                await stopDeployment(deployment.id);
            }
        }
        
        function openTestDialog(deployment) {
            testDeployment.value = deployment;
            testMessages.value = [];
            testInput.value = '';
            testCurrentContent.value = '';
            testStreaming.value = false;
            showTestDialog.value = true;
        }
        
        async function sendTestMessage() {
            if (!testInput.value.trim() || testStreaming.value) return;
            
            const userMessage = testInput.value.trim();
            testMessages.value.push({ role: 'user', content: userMessage });
            testInput.value = '';
            testStreaming.value = true;
            testCurrentContent.value = '';
            
            try {
                const response = await fetch(`${testDeployment.value.api_url}/chat/completions`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        model: testDeployment.value.model_name,
                        messages: testMessages.value.map(m => ({ role: m.role, content: m.content })),
                        stream: true
                    })
                });
                
                if (!response.ok) {
                    throw new Error('请求失败');
                }
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const data = line.slice(6);
                            if (data === '[DONE]') continue;
                            
                            try {
                                const json = JSON.parse(data);
                                const content = json.choices?.[0]?.delta?.content;
                                if (content) {
                                    testCurrentContent.value += content;
                                }
                            } catch (e) {}
                        }
                    }
                }
                
                if (testCurrentContent.value) {
                    testMessages.value.push({ role: 'assistant', content: testCurrentContent.value });
                }
            } catch (error) {
                ElMessage.error('请求失败: ' + error.message);
                testMessages.value.push({ role: 'assistant', content: '请求失败: ' + error.message });
            } finally {
                testStreaming.value = false;
                testCurrentContent.value = '';
            }
        }
        
        function handleMenuSelect(index) {
            activeMenu.value = index;
            
            if (index === 'datasets') loadDatasets();
            else if (index === 'training') { loadTasks(); loadBaseModels(); }
            else if (index === 'models') { loadModels(); loadDeployments(); }
            else if (index === 'deployments') loadDeployments();
            else if (index === 'community') loadCommunityPosts();
        }
        
        async function handleCommand(command) {
            if (command === 'logout') {
                localStorage.removeItem('token');
                localStorage.removeItem('user');
                window.location.href = '/';
            } else if (command === 'profile') {
                profileForm.value.username = user.value.username || '';
                profileForm.value.email = user.value.email || '';
                showProfileDialog.value = true;
            } else if (command === 'contact') {
                window.location.href = '/contact';
            } else if (command === 'recharge') {
                rechargeForm.value.points = 10;
                rechargeAmount.value = 1.00;
                currentOrder.value = null;
                showRechargeDialog.value = true;
            }
        }
        
        async function updateProfile() {
            if (!profileForm.value.username) {
                ElMessage.error('用户名不能为空');
                return;
            }
            
            updatingProfile.value = true;
            const result = await apiRequest(`${API_BASE}/user/profile`, {
                method: 'PUT',
                body: JSON.stringify({ username: profileForm.value.username })
            });
            updatingProfile.value = false;
            
            if (result && result.success) {
                user.value.username = profileForm.value.username;
                localStorage.setItem('user', JSON.stringify(user.value));
                ElMessage.success('更新成功');
                showProfileDialog.value = false;
            } else {
                ElMessage.error(result.message || '更新失败');
            }
        }
        
        function formatSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
        }
        
        function formatDate(dateStr) {
            const date = new Date(dateStr);
            return date.toLocaleString('zh-CN');
        }
        
        function getStatusType(status) {
            const types = {
                'pending': 'info', 'running': 'warning', 'completed': 'success',
                'failed': 'danger', 'cancelled': 'info', 'trained': 'success', 'training': 'warning'
            };
            return types[status] || 'info';
        }
        
        function getStatusText(status) {
            const texts = {
                'pending': '待处理', 'running': '训练中', 'completed': '已完成',
                'failed': '失败', 'cancelled': '已取消', 'trained': '已训练', 'training': '训练中'
            };
            return texts[status] || status;
        }
        
        function getDeploymentStatusType(status) {
            const types = { 'deploying': 'warning', 'active': 'success', 'stopped': 'info', 'failed': 'danger', 'unavailable': 'danger' };
            return types[status] || 'info';
        }
        
        function getDeploymentStatusText(status) {
            const texts = { 'deploying': '部署中', 'active': '运行中', 'stopped': '已停止', 'failed': '失败', 'unavailable': '不可用' };
            return texts[status] || status;
        }
        
        async function viewLogs(model) {
            currentModel.value = model;
            showLogDialog.value = true;
            await loadLogs(model.id);
        }
        
        async function loadLogs(modelId) {
            const result = await apiRequest(`${API_BASE}/logs/model/${modelId}`);
            if (result && result.success) {
                logs.value = result.data;
                await nextTick();
                if (logMessagesRef.value) {
                    logMessagesRef.value.scrollTop = logMessagesRef.value.scrollHeight;
                }
            }
        }
        
        function getLogType(type) {
            const types = { 'training': 'warning', 'deployment': 'success', 'system': 'info' };
            return types[type] || 'info';
        }
        
        function getLogLevel(level) {
            const levels = { 'INFO': 'info', 'WARNING': 'warning', 'ERROR': 'danger', 'DEBUG': 'info' };
            return levels[level] || 'info';
        }
        
        watch(() => rechargeForm.value.points, (newPoints) => {
            rechargeAmount.value = (newPoints / 10).toFixed(2);
        });
        
        async function createRechargeOrder() {
            if (!rechargeForm.value.points || rechargeForm.value.points < 10) {
                ElMessage.error('充值积分不能少于10');
                return;
            }
            
            creatingRechargeOrder.value = true;
            const result = await apiRequest(`${API_BASE}/payment/create-order`, {
                method: 'POST',
                body: JSON.stringify({ points: rechargeForm.value.points })
            });
            creatingRechargeOrder.value = false;
            
            if (result && result.success) {
                currentOrder.value = result.data;
                startCountdown(result.data.expires_in_seconds);
                ElMessage.success('订单创建成功，请扫码支付');
            } else {
                ElMessage.error(result.message || '创建订单失败');
            }
        }
        
        function startCountdown(seconds) {
            if (countdownTimer.value) {
                clearInterval(countdownTimer.value);
            }
            
            let remaining = seconds;
            updateCountdown(remaining);
            
            countdownTimer.value = setInterval(() => {
                remaining--;
                updateCountdown(remaining);
                
                if (remaining <= 0) {
                    clearInterval(countdownTimer.value);
                    countdown.value = '00:00';
                    currentOrder.value = null;
                    ElMessage.warning('订单已过期，请重新创建');
                }
            }, 1000);
        }
        
        function updateCountdown(seconds) {
            const minutes = Math.floor(seconds / 60);
            const secs = seconds % 60;
            countdown.value = `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        
        async function checkPaymentStatus() {
            checkingPayment.value = true;
            const result = await apiRequest(`${API_BASE}/payment/orders/${currentOrder.value.order_no}`);
            checkingPayment.value = false;
            
            if (result && result.success) {
                if (result.data.status === 'paid') {
                    ElMessage.success('支付成功！');
                    user.value.points = result.data.new_balance;
                    localStorage.setItem('user', JSON.stringify(user.value));
                    clearInterval(countdownTimer.value);
                    currentOrder.value = null;
                    showRechargeDialog.value = false;
                } else if (result.data.status === 'expired') {
                    ElMessage.error('订单已过期');
                    clearInterval(countdownTimer.value);
                    currentOrder.value = null;
                } else {
                    ElMessage.info('支付状态：' + result.data.status);
                }
            } else {
                ElMessage.error(result.message || '查询失败');
            }
        }
        
        async function refreshUserPoints() {
            const result = await apiRequest(`${API_BASE}/user/info`);
            if (result && result.success) {
                user.value.points = result.data.points;
                localStorage.setItem('user', JSON.stringify(user.value));
                ElMessage.success('积分已刷新');
            } else {
                ElMessage.error(result.message || '刷新失败');
            }
        }
        
        onMounted(() => {
            const savedUser = localStorage.getItem('user');
            if (savedUser) {
                try {
                    user.value = JSON.parse(savedUser);
                } catch (e) {}
            }
            loadUserInfo();
            loadDatasets();
            loadBaseModels();
            loadModels();
            loadDeployments();
        });
        
        return {
            user, activeMenu, datasets, tasks, models, deployments, baseModels, stats, modelsWithDeployment,
            showUploadDialog, showCreateTaskDialog, showTestDialog, showLogDialog, showDeployDialog, showProfileDialog, showCommunityCreateDialog, showTrainingLogDialog, showRenewDialog, showRechargeDialog,
            uploadFile, uploading, creating, deploying, taskForm, deployForm, profileForm, updatingProfile, communityPosts, communityPostForm, creatingCommunityPost,
            testDeployment, testMessages, testInput, testStreaming, testCurrentContent, testMessagesRef,
            currentModel, logs, logMessagesRef,
            trainingLogTask, trainingLogContent, loadingTrainingLog, trainingLogRef,
            renewDeployment, renewForm, renewing,
            rechargeForm, rechargeAmount, currentOrder, creatingRechargeOrder, checkingPayment, countdown, qrCodeUrl,
            handleMenuSelect, handleCommand, handleFileChange, uploadDataset, deleteDataset,
            createTask, cancelTask, restartTask, deleteTask, deleteModel, deployModel, confirmDeploy, stopDeployment, copyApiUrl, copyApiKey, updateProfile,
            loadCommunityPosts, createCommunityPost, deleteCommunityPost, handlePostCommand,
            isModelDeployed, stopDeploymentByModel, openTestDialog, sendTestMessage, viewLogs,
            viewTrainingLog, loadTrainingLog, openRenewDialog, confirmRenew, formatDateTime,
            formatSize, formatDate, getStatusType, getStatusText, getDeploymentStatusType, getDeploymentStatusText,
            getLogType, getLogLevel,
            createRechargeOrder, startCountdown, updateCountdown, checkPaymentStatus, refreshUserPoints
        };
    }
});

app.use(ElementPlus);
app.mount('#app');
