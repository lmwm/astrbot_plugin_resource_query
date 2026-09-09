/**
 * 模块注册中心
 * 管理所有模块的注册和加载
 */

const ModuleRegistry = {
  modules: {},
  
  // 注册模块
  register(name, config) {
    this.modules[name] = config;
  },
  
  // 获取所有已注册模块
  getAll() {
    return Object.entries(this.modules);
  },
  
  // 获取模块配置
  get(name) {
    return this.modules[name];
  },
  
  // 动态加载所有模块到页面
  async loadAll() {
    const navTabs = document.querySelector('.nav-tabs');
    const container = document.querySelector('.container');
    
    for (const [name, config] of this.getAll()) {
      try {
        // 创建导航标签
        const tab = document.createElement('button');
        tab.className = 'nav-tab';
        tab.textContent = config.icon + ' ' + config.title;
        tab.onclick = (e) => switchPage(name, e);
        navTabs.appendChild(tab);
        
        // 创建页面容器
        const pageDiv = document.createElement('div');
        pageDiv.className = 'page';
        pageDiv.id = 'page-' + name;
        pageDiv.innerHTML = config.template;
        container.appendChild(pageDiv);
        
        console.log(`模块 ${name} 加载成功`);
      } catch (e) {
        console.error(`模块 ${name} 加载失败:`, e);
      }
    }
  }
};

// 导出
window.ModuleRegistry = ModuleRegistry;
