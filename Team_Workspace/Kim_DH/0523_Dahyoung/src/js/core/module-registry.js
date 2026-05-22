/**
 * module-registry.js
 * Central registry for managing all feature modules.
 * Enables easier addition of new modules without modifying central initialization.
 */

class ModuleRegistry {
  constructor() {
    this.modules = new Map();
  }

  /**
   * Register a module with the registry
   * @param {string} name - Module identifier
   * @param {Object} module - Module object with init/render/destroy methods
   */
  register(name, module) {
    if (this.modules.has(name)) {
      console.warn(`Module "${name}" already registered, overwriting`);
    }
    this.modules.set(name, module);
  }

  /**
   * Get a registered module
   * @param {string} name - Module identifier
   * @returns {Object|null} Module object or null
   */
  get(name) {
    return this.modules.get(name) || null;
  }

  /**
   * Check if module is registered
   * @param {string} name - Module identifier
   * @returns {boolean}
   */
  has(name) {
    return this.modules.has(name);
  }

  /**
   * Initialize all modules
   * @param {Object} context - Context object passed to init() of each module
   * @returns {Promise<Object>} Results of initialization
   */
  async initAll(context = {}) {
    const results = {};
    for (const [name, module] of this.modules) {
      try {
        if (typeof module.init === 'function') {
          results[name] = await module.init(context);
        }
      } catch (e) {
        console.error(`Failed to initialize module "${name}":`, e);
        results[name] = { error: e };
      }
    }
    return results;
  }

  /**
   * Render all modules (optional method)
   * @param {Object} context - Context object passed to render() of each module
   * @returns {Promise<Object>} Results of rendering
   */
  async renderAll(context = {}) {
    const results = {};
    for (const [name, module] of this.modules) {
      try {
        if (typeof module.render === 'function') {
          results[name] = await module.render(context);
        }
      } catch (e) {
        console.error(`Failed to render module "${name}":`, e);
        results[name] = { error: e };
      }
    }
    return results;
  }

  /**
   * Destroy all modules (cleanup on unload)
   * @returns {Promise<Object>} Results of destruction
   */
  async destroyAll() {
    const results = {};
    for (const [name, module] of this.modules) {
      try {
        if (typeof module.destroy === 'function') {
          results[name] = await module.destroy();
        }
      } catch (e) {
        console.error(`Failed to destroy module "${name}":`, e);
        results[name] = { error: e };
      }
    }
    return results;
  }

  /**
   * Get list of all registered module names
   * @returns {Array<string>}
   */
  getModuleNames() {
    return Array.from(this.modules.keys());
  }

  /**
   * Get count of registered modules
   * @returns {number}
   */
  count() {
    return this.modules.size;
  }
}

export const moduleRegistry = new ModuleRegistry();
