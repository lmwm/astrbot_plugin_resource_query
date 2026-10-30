// 资源查询插件 Views 前端：消息模板编辑、模块设置与变量保存
//
// 所有脚本共享同一全局作用域，按 index.html 中的顺序加载；
// 工具与状态由 base.js 提供。
'use strict';

  //  模板编辑

  function renderTemplateTags(moduleName) {
    const box = $('account-variable-tags');
    if (!box) return;

    box.innerHTML = variablesOf(moduleName)
      .filter((v) => v.show !== false)
      .map((v) => '<button class="variable-tag" data-action="insert-variable" data-name="' + esc(v.name) + '">' +
        esc(v.desc || v.name) + '</button>')
      .join('');
  }

  function updateTemplatePreview(moduleName) {
    const textarea = $('account-template');
    const preview = $('account-template-preview');
    if (!textarea || !preview) return;

    let text = textarea.value || defaultTemplate(moduleName);

    variablesOf(moduleName).forEach((v) => {
      text = text.split('{' + v.name + '}').join(v.default || '');
    });

    preview.textContent = text || '（请在左侧输入模板）';
  }

  function insertVariable(name) {
    const textarea = $('account-template');
    if (!textarea || !state.editing) return;

    const token = '{' + name + '}';
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;

    textarea.value = textarea.value.slice(0, start) + token + textarea.value.slice(end);
    textarea.selectionStart = textarea.selectionEnd = start + token.length;
    textarea.focus();

    updateTemplatePreview(state.editing.module.name);
  }

  //  模块设置与变量保存

  async function saveModuleConfig(moduleName) {
    const mod = moduleByName(moduleName);
    if (!mod) return;

    const payload = {};

    (mod.config_fields || []).forEach((field) => {
      const el = $('cfg-' + mod.name + '-' + field.key);
      if (!el) return;

      if (field.type === 'bool') {
        payload[field.key] = el.checked;
      } else if (field.type === 'int') {
        payload[field.key] = toInt(el.value, field.default === undefined ? 0 : field.default);
      } else {
        payload[field.key] = el.value.trim();
      }
    });

    try {
      await api.post(mod.name + '/config', payload);
      mod.config = Object.assign({}, mod.config, payload);
      toast('设置已保存');
    } catch (e) {
      toast('保存失败：' + e.message, 'error');
    }
  }

  async function saveVariables(moduleName) {
    const mod = moduleByName(moduleName);
    if (!mod) return;

    const rows = Array.from(document.querySelectorAll('#vars-' + moduleName + ' [data-var="name"]'));

    const variables = rows.map((el) => {
      const index = el.dataset.index;
      const pick = (key) => document.querySelector(
        '#vars-' + moduleName + ' [data-var="' + key + '"][data-index="' + index + '"]'
      );

      const descEl = pick('desc');
      const defaultEl = pick('default');
      const showEl = pick('show');

      return {
        name: el.value.trim(),
        desc: descEl ? descEl.value.trim() : '',
        default: defaultEl ? defaultEl.value : '',
        show: showEl ? showEl.checked : true,
      };
    }).filter((v) => v.name);

    try {
      await api.post('template-vars', { platform: moduleName, variables });
      await loadVars();
      renderVarTable(mod);
      renderTemplateTags(moduleName);
      toast('变量配置已保存');
    } catch (e) {
      toast('保存失败：' + e.message, 'error');
    }
  }

  /** 删除变量只改内存，需点「保存变量」才落库，误删可刷新恢复 */
  function removeVariable(moduleName, index) {
    const list = variablesOf(moduleName).slice();
    if (index < 0 || index >= list.length) return;

    list.splice(index, 1);
    state.vars[moduleName] = { variables: list };

    const mod = moduleByName(moduleName);
    if (mod) renderVarTable(mod);

    toast('已移除，点击「保存变量」后生效');
  }
