/**
 * EgoLink DevBench State Management & Event Bus
 * Credentials are kept only in the user's browser localStorage.
 */

const STORAGE_KEYS = {
  HUB_TOKEN: 'egolink_hub_token',
  GUARDIAN_TOKEN: 'egolink_guardian_token',
  DEVICE_ID: 'egolink_selected_device',
  REFRESH_INTERVAL: 'egolink_refresh_interval',
  ACTIVE_TAB: 'egolink_active_tab'
};

class StateManager {
  constructor() {
    this.hubToken = localStorage.getItem(STORAGE_KEYS.HUB_TOKEN) || '';
    this.guardianToken = localStorage.getItem(STORAGE_KEYS.GUARDIAN_TOKEN) || this.hubToken || '';
    this.selectedDeviceId = localStorage.getItem(STORAGE_KEYS.DEVICE_ID) || 'ego-link-001';
    this.refreshInterval = parseInt(localStorage.getItem(STORAGE_KEYS.REFRESH_INTERVAL) || '10', 10);
    this.activeTab = localStorage.getItem(STORAGE_KEYS.ACTIVE_TAB) || 'overview';

    this.devices = [];
    this.collectionSummary = null;
    this.photos = [];
    this.rawFrames = [];
    this.commands = [];
    this.locationState = null;
    this.hubState = null;
    this.health = null;

    this.listeners = new Map();
    this.timer = null;
  }

  saveCredentials({ deviceId, hubToken, guardianToken }) {
    if (deviceId !== undefined && deviceId.trim()) {
      this.selectedDeviceId = deviceId.trim();
      localStorage.setItem(STORAGE_KEYS.DEVICE_ID, this.selectedDeviceId);
    }
    if (hubToken !== undefined) {
      this.hubToken = hubToken.trim();
      localStorage.setItem(STORAGE_KEYS.HUB_TOKEN, this.hubToken);
    }
    if (guardianToken !== undefined) {
      this.guardianToken = (guardianToken.trim() || this.hubToken || '');
      localStorage.setItem(STORAGE_KEYS.GUARDIAN_TOKEN, this.guardianToken);
    }
    this.emit('credentialsChanged', {
      deviceId: this.selectedDeviceId,
      hubToken: this.hubToken,
      guardianToken: this.guardianToken
    });
  }

  clearCredentials() {
    this.hubToken = '';
    this.guardianToken = '';
    localStorage.removeItem(STORAGE_KEYS.HUB_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.GUARDIAN_TOKEN);
    this.emit('credentialsChanged', {
      deviceId: this.selectedDeviceId,
      hubToken: '',
      guardianToken: ''
    });
  }

  selectDevice(deviceId) {
    if (!deviceId) return;
    this.selectedDeviceId = deviceId.trim();
    localStorage.setItem(STORAGE_KEYS.DEVICE_ID, this.selectedDeviceId);
    this.emit('deviceChanged', this.selectedDeviceId);
  }

  setActiveTab(tabName) {
    this.activeTab = tabName;
    localStorage.setItem(STORAGE_KEYS.ACTIVE_TAB, tabName);
    this.emit('tabChanged', tabName);
  }

  setRefreshInterval(seconds) {
    this.refreshInterval = parseInt(seconds, 10);
    localStorage.setItem(STORAGE_KEYS.REFRESH_INTERVAL, String(this.refreshInterval));
    this.emit('refreshIntervalChanged', this.refreshInterval);
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event).add(callback);
    return () => this.off(event, callback);
  }

  off(event, callback) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).delete(callback);
    }
  }

  emit(event, data) {
    if (!this.listeners.has(event)) return;
    for (const callback of this.listeners.get(event)) {
      try {
        callback(data);
      } catch (err) {
        console.error(`Error in event listener for ${event}:`, err);
      }
    }
  }
}

export const state = new StateManager();
