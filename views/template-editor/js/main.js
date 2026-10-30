// 资源查询插件 Views 前端：刷新、事件委托与初始化
//
// 所有脚本共享同一全局作用域，按 index.html 中的顺序加载；
// 工具与状态由 base.js 提供。
'use strict';

  //  刷新

  async function refreshAccounts() {
    try {
      await loadAccounts();
    } catch (e) {
      toast('账号列表刷新失败：' + e.message, 'error');
      return;
    }

    state.modules.forEach((mod) => {
      if (mod.supports_accounts) renderAccountList(mod);
    });
  }

  async function reloadAll() {
    await loadAll();

    if (!state.activeModule || !moduleByName(state.activeModule)) {
      state.activeModule = state.modules.length ? state.modules[0].name : '';
    }

    $('version').textContent = state.version ? 'v' + state.version : '';
    renderNav();
    renderPages();
  }

  function closeModal(id) {
    const el = $(id);
    if (el) el.classList.remove('active');
  }

  //  事件绑定（委托，无内联事件）

  async function onClick(event) {
    const target = event.target.closest('[data-action]');
    if (!target) return;

    const action = target.dataset.action;
    const moduleName = target.dataset.module;

    switch (action) {
      case 'select-module':
        selectModule(moduleName);
        break;

      case 'select-subtab':
        selectSubTab(moduleName, target.dataset.tab);
        break;

      case 'select-account-tab':
        selectAccountTab(target.dataset.tab);
        break;

      case 'select-group':
        selectGroup(target.dataset.group);
        break;

      case 'reset-field':
        resetField(target.dataset.key);
        break;

      case 'toggle-password': {
        const input = $(target.dataset.target);
        if (input) {
          const showing = input.type === 'text';
          input.type = showing ? 'password' : 'text';
          target.textContent = showing ? '显示' : '隐藏';
        }
        break;
      }

      case 'reload':
        await reloadAll();
        toast('已刷新');
        break;

      case 'add-account':
        openAccountModal(moduleName, '');
        break;

      case 'edit-account':
        openAccountModal(moduleName, target.dataset.file);
        break;

      case 'delete-account':
        askDelete(moduleName, target.dataset.file, target.dataset.name);
        break;

      case 'confirm-delete':
        await confirmDelete();
        break;

      case 'close-delete-modal':
        state.pendingDelete = null;
        closeModal('delete-modal');
        break;

      case 'close-account-modal':
        closeModal('account-modal');
        break;

      case 'save-account':
        if (await saveAccount()) {
          closeModal('account-modal');
          toast('已保存');
        }
        break;

      case 'login-account':
        await loginAccount();
        break;

      case 'test-account':
        await testAccount();
        break;

      case 'reset-template':
        if (state.editing) {
          $('account-template').value = defaultTemplate(state.editing.module.name);
          updateTemplatePreview(state.editing.module.name);
        }
        break;

      case 'insert-variable':
        insertVariable(target.dataset.name);
        break;

      case 'save-config':
        await saveModuleConfig(moduleName);
        break;

      case 'save-vars':
        await saveVariables(moduleName);
        break;

      case 'remove-var':
        removeVariable(moduleName, toInt(target.dataset.index, -1));
        break;

      default:
        break;
    }
  }

  function onInput(event) {
    if (event.target && event.target.id === 'account-template' && state.editing) {
      updateTemplatePreview(state.editing.module.name);
    }
  }

  function bindEvents() {
    document.addEventListener('click', onClick);
    document.addEventListener('input', onInput);

    // 点击遮罩关闭
    document.querySelectorAll('.modal-overlay').forEach((overlay) => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal(overlay.id);
      });
    });
  }

  //  初始化

  function showFatal(message) {
    const box = $('boot-error');
    if (box) box.innerHTML = '<div class="fatal">' + esc(message) + '</div>';
  }

  async function init() {
    if (!bridge) {
      showFatal('页面桥接未就绪（bridge SDK 未加载），请刷新页面重试。');
      return;
    }

    try {
      await bridge.ready();
    } catch (e) {
      showFatal('页面初始化失败：' + (e && e.message ? e.message : e));
      return;
    }

    bindEvents();
    await loadAll();

    if (state.modules.length) {
      state.activeModule = state.modules[0].name;
    }

    $('version').textContent = state.version ? 'v' + state.version : '';
    renderNav();
    renderPages();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
