// 资源查询插件 Views 前端：状态、基础工具、API 与数据加载
//
// 所有脚本共享同一全局作用域，按 index.html 中的顺序加载；
// 工具与状态由 base.js 提供。
'use strict';

  // AstrBot 新版 bridge 名为 AstrBotPluginView，旧版为 AstrBotPluginPage
  const bridge = window.AstrBotPluginView || window.AstrBotPluginPage;

  //  状态

  const state = {
    version: '',
    modules: [],
    accounts: [],
    vars: {},
    activeModule: '',
    subTabs: {},          // 模块名 → 当前页面标签（accounts / variables / settings）
    editing: null,        // { module, filename, account, activeTab, activeGroup }
    pendingDelete: null,  // { module, filename, name }
    toastTimer: null,
  };

  //  基础工具

  const $ = (id) => document.getElementById(id);

  /** HTML 转义：任何要拼进 innerHTML 的外部数据都必须先经过它 */
  function esc(value) {
    const text = value === undefined || value === null ? '' : String(value);
    return text.replace(/[&<>"']/g, (c) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    })[c]);
  }

  function toast(message, type) {
    const el = $('toast');
    if (!el) return;

    el.textContent = message;
    el.className = 'toast show' + (type === 'error' ? ' error' : '');

    if (state.toastTimer) clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => {
      el.className = 'toast';
    }, 3000);
  }

  /** 在账号模态框内部显示状态，避免提示落到隐藏容器里 */
  function setStatus(message, type) {
    const el = $('account-status');
    if (!el) return;

    if (!message) {
      el.style.display = 'none';
      return;
    }

    el.textContent = message;
    el.className = 'status-box ' + (type || 'ok');
    el.style.display = '';
  }

  /** 整数解析：保留 0（"0 表示不限制"这类语义不能被 || 吞掉） */
  function toInt(value, fallback) {
    const num = parseInt(value, 10);
    if (Number.isNaN(num)) return fallback === undefined ? 0 : fallback;
    return num;
  }

  //  API

  /** 统一请求：后端返回 error 时抛错，由调用方决定如何提示 */
  async function request(endpoint, payload, method) {
    const result = method === 'GET'
      ? await bridge.apiGet(endpoint, payload)
      : await bridge.apiPost(endpoint, payload);

    if (result && result.status === 'error') {
      throw new Error(result.message || '请求失败');
    }

    return result || {};
  }

  const api = {
    get: (endpoint, params) => request(endpoint, params, 'GET'),
    post: (endpoint, body) => request(endpoint, body, 'POST'),
  };

  //  数据加载

  async function loadModules() {
    const data = await api.get('modules');
    state.version = data.version || '';
    state.modules = data.modules || [];
  }

  async function loadAccounts() {
    const data = await api.get('accounts');
    state.accounts = data.accounts || [];
  }

  async function loadVars() {
    state.vars = await api.get('template-vars');
  }

  /** 加载各模块自有配置：单个模块失败只影响它自己，绝不用空值覆盖后端配置 */
  async function loadModuleConfigs() {
    await Promise.all(state.modules.map(async (mod) => {
      if (!mod.config_fields || !mod.config_fields.length) {
        mod.config = {};
        return;
      }
      try {
        mod.config = await api.get(mod.name + '/config');
      } catch (e) {
        mod.config = null; // null 表示"未取到"，渲染时回退到字段默认值
      }
    }));
  }

  /** 并行加载全部数据：任一失败只提示，不中断其余 */
  async function loadAll() {
    const problems = [];

    await Promise.all([
      loadModules().catch((e) => { problems.push('模块列表(' + e.message + ')'); }),
      loadAccounts().catch((e) => { problems.push('账号列表(' + e.message + ')'); }),
      loadVars().catch((e) => { problems.push('模板变量(' + e.message + ')'); }),
    ]);

    await loadModuleConfigs();

    if (problems.length) {
      toast('部分数据加载失败：' + problems.join('，'), 'error');
    }
  }

  //  查询辅助

  const moduleByName = (name) => state.modules.find((m) => m.name === name) || null;
  const accountsOf = (name) => state.accounts.filter((a) => a.platform === name);
  const variablesOf = (name) => (state.vars[name] && state.vars[name].variables) || [];

  const accountLabel = (acc, fallback) =>
    acc.name || acc.account || acc.phone || fallback || '未命名账号';

  const defaultTemplate = (name) => {
    const mod = moduleByName(name);
    return (mod && mod.default_template) || '';
  };

  /** 字段所属分组（支持字符串或数组） */
  function groupsOfField(field) {
    if (!field.group) return [];
    return Array.isArray(field.group) ? field.group : [field.group];
  }

  const fieldsInGroup = (fields, key) =>
    (fields || []).filter((f) => groupsOfField(f).includes(key));

  /** 未归入任何已声明分组的字段（始终显示在账号配置顶部） */
  function ungroupedFields(mod) {
    const known = (mod.account_groups || []).map((g) => g.key);
    return (mod.account_fields || []).filter((f) => {
      const groups = groupsOfField(f);
      return groups.length === 0 || groups.every((k) => !known.includes(k));
    });
  }

  const accountTabGroups = (mod) =>
    (mod.account_groups || []).filter((g) => (g.mode || 'tab') === 'tab');

  const accountInlineGroups = (mod) =>
    (mod.account_groups || []).filter((g) => g.mode === 'inline');
