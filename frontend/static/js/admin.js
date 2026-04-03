const { createApp, ref, onMounted } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

const API_BASE = '/api';

const app = createApp({
    setup() {
        const user = ref({});
        const activeMenu = ref('dashboard');
        const users = ref([]);
        const devices = ref([]);
        const tasks = ref([]);
        const deployments = ref([]);
        const datasets = ref([]);
        const dashboard = ref({
            total_users: 0,
            total_devices: 0,
            online_devices: 0,
            total_models: 0,
            total_deployments: 0,
            active_deployments: 0,
            pending_tasks: 0,
            running_tasks: 0
        });
        
        const token = localStorage.getItem('token');
        
        async function apiRequest(url, options = {}) {
            const headers = {
                'Content-Type': 'application/json',
                ...options.headers
            };
            
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            
            const response = await fetch(url, {
                ...options,
                headers
            });
            
            if (response.status === 401) {
                localStorage.removeItem('token');
                localStorage.removeItem('user');
                window.location.href = '/';
                return null;
            }
            
            return await response.json();
        }
        
        async function loadUserInfo() {
            const result = await apiRequest(`${API_BASE}/user/info`);
            if (result && result.success) {
                user.value = result.data;
            }
        }
        
        async function loadDashboard() {
            const result = await apiRequest(`${API_BASE}/admin/dashboard`);
            if (result && result.success) {
                dashboard.value = result.data;
            }
        }
        
        async function loadUsers() {
            const result = await apiRequest(`${API_BASE}/user/all`);
            if (result && result.success) {
                users.value = result.data;
            }
        }
        
        async function loadDevices() {
            const result = await apiRequest(`${API_BASE}/admin/devices`);
            if (result && result.success) {
                devices.value = result.data;
            }
        }
        
        async function loadTasks() {
            const result = await apiRequest(`${API_BASE}/training/all`);
            if (result && result.success) {
                tasks.value = result.data;
            }
        }
        
        async function loadDatasets() {
            const result = await apiRequest(`${API_BASE}/dataset/all`);
            if (result && result.success) {
                datasets.value = result.data;
            }
        }
        
        async function loadDeployments() {
            const result = await apiRequest(`${API_BASE}/deployments/all`);
            if (result && result.success) {
                deployments.value = result.data;
            }
        }
        
        async function banUser(id) {
            try {
                await ElMessageBox.confirm('确定要封禁这个用户吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const result = await apiRequest(`${API_BASE}/user/${id}/ban`, {
                    method: 'POST'
                });
                
                if (result && result.success) {
                    ElMessage.success('封禁成功');
                    await loadUsers();
                } else {
                    ElMessage.error(result.message || '封禁失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    ElMessage.error('封禁失败');
                }
            }
        }
        
        async function unbanUser(id) {
            try {
                await ElMessageBox.confirm('确定要解封这个用户吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const result = await apiRequest(`${API_BASE}/user/${id}/unban`, {
                    method: 'POST'
                });
                
                if (result && result.success) {
                    ElMessage.success('解封成功');
                    await loadUsers();
                } else {
                    ElMessage.error(result.message || '解封失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    ElMessage.error('解封失败');
                }
            }
        }
        
        async function deleteDevice(id) {
            try {
                await ElMessageBox.confirm('确定要删除这个设备吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const result = await apiRequest(`${API_BASE}/admin/devices/${id}`, {
                    method: 'DELETE'
                });
                
                if (result && result.success) {
                    ElMessage.success('删除成功');
                    await loadDevices();
                } else {
                    ElMessage.error(result.message || '删除失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    ElMessage.error('删除失败');
                }
            }
        }
        
        async function checkOfflineDevices() {
            const result = await apiRequest(`${API_BASE}/admin/devices/check-offline`, {
                method: 'POST'
            });
            
            if (result && result.success) {
                ElMessage.success(result.message);
                await loadDevices();
                await loadTasks();
            } else {
                ElMessage.error(result.message || '检查失败');
            }
        }
        
        async function deleteDataset(id) {
            try {
                await ElMessageBox.confirm('确定要删除这个数据集吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const result = await apiRequest(`${API_BASE}/datasets/admin/${id}`, {
                    method: 'DELETE'
                });
                
                if (result && result.success) {
                    ElMessage.success('删除成功');
                    await loadDatasets();
                } else {
                    ElMessage.error(result.message || '删除失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    ElMessage.error('删除失败');
                }
            }
        }
        
        async function checkExpiredDeployments() {
            const result = await apiRequest(`${API_BASE}/admin/deployments/check-expired`, {
                method: 'POST'
            });
            
            if (result && result.success) {
                ElMessage.success(result.message);
                await loadDeployments();
            } else {
                ElMessage.error(result.message || '检查失败');
            }
        }
        
        function handleMenuSelect(index) {
            activeMenu.value = index;
            
            if (index === 'dashboard') {
                loadDashboard();
            } else if (index === 'users') {
                loadUsers();
            } else if (index === 'devices') {
                loadDevices();
            } else if (index === 'datasets') {
                loadDatasets();
            } else if (index === 'tasks') {
                loadTasks();
            } else if (index === 'deployments') {
                loadDeployments();
            }
        }
        
        function logout() {
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            window.location.href = '/';
        }
        
        function formatDate(dateStr) {
            if (!dateStr) return '-';
            const date = new Date(dateStr);
            return date.toLocaleString('zh-CN');
        }
        
        function formatSize(bytes) {
            if (!bytes) return '0 B';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
        }
        
        function getUserStatusType(status) {
            const types = {
                'active': 'success',
                'inactive': 'info',
                'banned': 'danger'
            };
            return types[status] || 'info';
        }
        
        function getDeviceStatusType(status) {
            const types = {
                'online': 'success',
                'offline': 'info',
                'busy': 'warning'
            };
            return types[status] || 'info';
        }
        
        function getTaskStatusType(status) {
            const types = {
                'pending': 'info',
                'running': 'warning',
                'completed': 'success',
                'failed': 'danger',
                'cancelled': 'info'
            };
            return types[status] || 'info';
        }
        
        function getDeploymentStatusType(status) {
            const types = {
                'active': 'success',
                'stopped': 'info',
                'failed': 'danger',
                'unavailable': 'danger'
            };
            return types[status] || 'info';
        }
        
        onMounted(() => {
            const savedUser = localStorage.getItem('user');
            if (savedUser) {
                user.value = JSON.parse(savedUser);
            }
            
            if (user.value.role !== 'admin') {
                window.location.href = '/';
                return;
            }
            
            loadUserInfo();
            loadDashboard();
        });
        
        return {
            user,
            activeMenu,
            users,
            devices,
            tasks,
            deployments,
            datasets,
            dashboard,
            handleMenuSelect,
            logout,
            banUser,
            unbanUser,
            deleteDevice,
            checkOfflineDevices,
            checkExpiredDeployments,
            deleteDataset,
            formatDate,
            formatSize,
            getUserStatusType,
            getDeviceStatusType,
            getTaskStatusType,
            getDeploymentStatusType
        };
    }
});

app.use(ElementPlus);
app.mount('#app');
