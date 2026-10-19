/**
 * Greek Courier Tracker card.
 *
 * Bundled with the integration and loaded automatically, so it can be added
 * from the dashboard card picker without installing anything else:
 *
 *   type: custom:greek-courier-tracker-card
 *   title: Shipments          # optional
 *   show_add_form: true       # optional, default true
 *   show_delivered: true      # optional, default true
 *   entities: [...]           # optional, default: all tracking sensors
 *   entry_id: ...             # optional, config entry that new numbers go to
 */

const CARD_TYPE = "greek-courier-tracker-card";
const DOMAIN = "greek_courier_tracker";
const PENDING_TIMEOUT_MS = 90 * 1000;
// Sensors are briefly unavailable while the integration (re)loads
const RELOAD_GRACE_MS = 60 * 1000;

// Keep in sync with COURIER_LIST in config_flow.py
const COURIERS = [
  ["auto", { en: "Auto-detect", el: "Αυτόματος εντοπισμός" }],
  ["acs", "ACS Courier"],
  ["box_now", "Box Now"],
  ["courier_center", "Courier Center"],
  ["elta", { en: "ELTA Courier", el: "ΕΛΤΑ Courier" }],
  ["geniki", { en: "Geniki Taxydromiki", el: "Γενική Ταχυδρομική" }],
  ["skroutz", "Skroutz Last Mile"],
  ["speedex", "SpeedEx"],
  ["svuum", "Svuum"],
];

const STRINGS = {
  en: {
    title: "Shipments",
    active: (count) => `${count} active`,
    tracking_number: "Tracking number",
    name: "Name (optional)",
    courier: "Courier",
    owner: "Owner",
    shared: "Shared",
    change_owner: "Change owner",
    add: "Add",
    added: "Added. Looking it up with the couriers…",
    required: "Enter a tracking number",
    exists: "This tracking number is already tracked",
    searching: "Looking it up with the couriers…",
    empty: "No shipments are being tracked. Add a tracking number above.",
    empty_no_form: "No shipments are being tracked.",
    updates: (count) => (count === 1 ? "1 update" : `${count} updates`),
    remove: "Remove",
    confirm_remove: "Remove?",
    delivered: "Delivered",
    not_found: "Not found yet",
    unavailable: "Unavailable",
    expected: "Expected",
  },
  el: {
    title: "Αποστολές",
    active: (count) => (count === 1 ? "1 ενεργή" : `${count} ενεργές`),
    tracking_number: "Αριθμός αποστολής",
    name: "Όνομα (προαιρετικό)",
    courier: "Εταιρεία",
    owner: "Ιδιοκτήτης",
    shared: "Κοινό",
    change_owner: "Αλλαγή ιδιοκτήτη",
    add: "Προσθήκη",
    added: "Προστέθηκε. Αναζήτηση στις εταιρείες…",
    required: "Γράψε έναν αριθμό αποστολής",
    exists: "Αυτός ο αριθμός παρακολουθείται ήδη",
    searching: "Αναζήτηση στις εταιρείες…",
    empty: "Δεν παρακολουθείται καμία αποστολή. Πρόσθεσε έναν αριθμό από πάνω.",
    empty_no_form: "Δεν παρακολουθείται καμία αποστολή.",
    updates: (count) => (count === 1 ? "1 ενημέρωση" : `${count} ενημερώσεις`),
    remove: "Αφαίρεση",
    confirm_remove: "Σίγουρα;",
    delivered: "Παραδόθηκε",
    not_found: "Δεν βρέθηκε ακόμα",
    unavailable: "Μη διαθέσιμο",
    expected: "Αναμένεται",
  },
};

const CATEGORY_ORDER = { in_transit: 0, created: 1, unknown: 2, error: 2, delivered: 3 };
const GREEK = /[Ͱ-Ͽἀ-῿]/;

const STYLES = `
  :host { display: block; container-type: inline-size; }
  ha-card { padding: 16px; }
  .header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
  .title { display: flex; align-items: center; gap: 8px; font-size: 18px; font-weight: 500; color: var(--primary-text-color); }
  .count { font-size: 13px; color: var(--secondary-text-color); }
  form { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1.5fr) minmax(0, 1.5fr) auto; gap: 8px; }
  form.with-owner { grid-template-columns: minmax(0, 2fr) minmax(0, 1.5fr) minmax(0, 1.5fr) minmax(0, 1.2fr) auto; }
  input, select { font: inherit; font-size: 14px; color: var(--primary-text-color); background: var(--secondary-background-color, rgba(127, 127, 127, 0.08)); border: 1px solid var(--divider-color); border-radius: 8px; height: 40px; padding: 0 10px; min-width: 0; box-sizing: border-box; width: 100%; }
  input::placeholder { color: var(--secondary-text-color); }
  input:focus, select:focus { outline: none; border-color: var(--primary-color); }
  button.add { font: inherit; font-size: 14px; font-weight: 500; height: 40px; padding: 0 14px; border: none; border-radius: 8px; background: var(--primary-color); color: var(--text-primary-color, #fff); display: inline-flex; align-items: center; justify-content: center; gap: 6px; cursor: pointer; white-space: nowrap; }
  button.add[disabled] { opacity: 0.6; cursor: progress; }
  button.add ha-icon { --mdc-icon-size: 18px; }
  .msg { font-size: 12px; min-height: 16px; margin: 6px 2px 2px; color: var(--secondary-text-color); }
  .msg.error { color: var(--error-color); }
  .row { border-top: 1px solid var(--divider-color); padding: 12px 0; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .name { font-weight: 500; color: var(--primary-text-color); cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .badge { flex: none; font-size: 12px; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--divider-color); color: var(--secondary-text-color); white-space: nowrap; }
  .badge.ok { border-color: transparent; color: var(--success-color, #43a047); background: rgba(var(--rgb-success-color, 67, 160, 71), 0.15); }
  .badge.ok ha-icon { --mdc-icon-size: 14px; vertical-align: -2px; }
  .status { font-size: 14px; margin-top: 4px; color: var(--primary-text-color); }
  .status.muted { color: var(--secondary-text-color); }
  .bar { display: flex; gap: 4px; margin-top: 10px; }
  .bar i { flex: 1; height: 4px; border-radius: 2px; background: var(--divider-color); }
  .bar i.on { background: var(--primary-color); }
  .bar i.done { background: var(--success-color, #43a047); }
  .bar.pending i { animation: pulse 1.4s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.35; } }
  .meta { display: flex; align-items: flex-start; justify-content: space-between; gap: 4px 12px; margin-top: 8px; font-size: 13px; color: var(--secondary-text-color); }
  .info { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 14px; min-width: 0; }
  .actions { flex: none; display: flex; align-items: center; gap: 12px; }
  .meta ha-icon { --mdc-icon-size: 16px; vertical-align: -3px; margin-right: 2px; }
  .actions ha-icon { margin-right: 0; }
  .mono { font-family: var(--code-font-family, ui-monospace, monospace); }
  button.link { font: inherit; font-size: 13px; color: inherit; background: none; border: none; padding: 0; cursor: pointer; display: inline-flex; align-items: center; }
  button.link:hover { color: var(--primary-text-color); }
  button.remove.armed { color: var(--error-color); }
  select.owner-edit { width: auto; height: 28px; font-size: 13px; padding: 0 6px; }
  .timeline { margin: 10px 0 0 6px; padding-left: 14px; border-left: 2px solid var(--divider-color); font-size: 13px; color: var(--primary-text-color); }
  .event { margin-bottom: 8px; }
  .event:last-child { margin-bottom: 0; }
  .event .when { color: var(--secondary-text-color); }
  .empty { border-top: 1px solid var(--divider-color); padding: 14px 0 2px; font-size: 14px; color: var(--secondary-text-color); }
  @container (max-width: 520px) {
    form { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
    form.with-owner { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
    form input[name="tracking_number"], form select[name="owner"], form button.add { grid-column: 1 / -1; }
  }
`;

const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);

/** Parse the different courier date formats into a label and a sortable key. */
function parseWhen(date, time) {
  if (!date) return null;
  const hhmm = (time || "").slice(0, 5);
  let match = String(date).match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  let year, month, day;
  if (match) {
    [, year, month, day] = match;
  } else if ((match = String(date).match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/))) {
    [, day, month, year] = match;
  } else {
    return { label: [date, hhmm].filter(Boolean).join(" "), key: "" };
  }
  month = month.padStart(2, "0");
  day = day.padStart(2, "0");
  const sameYear = Number(year) === new Date().getFullYear();
  return {
    label: `${day}/${month}${sameYear ? "" : `/${year}`}${hhmm ? ` ${hhmm}` : ""}`,
    key: `${year}-${month}-${day} ${hhmm}`,
  };
}

/** "2026-10-21" or "2026-10-21T12:00+03:00" -> label for the expected delivery. */
function parseEta(value) {
  const match = String(value || "").match(/^(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?/);
  return match ? parseWhen(match[1], match[2] || "") : null;
}

class GreekCourierTrackerCard extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._expanded = new Set();
    this._pending = new Map();
    this._armedRemove = null;
    this._editingOwner = null;
    this._signature = "";
    this._lastGood = new Map();
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = { show_add_form: true, show_delivered: true, ...(config || {}) };
    this._built = false;
    this._signature = "";
    if (this._hass) this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  getCardSize() {
    return 2 + 2 * this._shipments().length;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  get _lang() {
    const language = this._hass?.locale?.language || this._hass?.language || "en";
    return language.startsWith("el") ? "el" : "en";
  }

  get _t() {
    return STRINGS[this._lang];
  }

  _courierLabel(label) {
    return typeof label === "string" ? label : label[this._lang];
  }

  /** People with a Home Assistant user: they can own shipments. */
  _people() {
    if (!this._hass) return [];
    return Object.values(this._hass.states)
      .filter((stateObj) => stateObj.entity_id.startsWith("person.") && stateObj.attributes.user_id)
      .map((stateObj) => ({
        entityId: stateObj.entity_id,
        userId: stateObj.attributes.user_id,
        name: stateObj.attributes.friendly_name || stateObj.entity_id,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  /** Tracking sensors of this integration, as plain shipment objects. */
  _shipments() {
    if (!this._hass) return [];
    const { states, entities, devices } = this._hass;
    const ids = Array.isArray(this._config.entities)
      ? this._config.entities
      : Object.keys(states).filter(
          (id) =>
            id.startsWith("sensor.") &&
            (entities?.[id]?.platform === DOMAIN || id.startsWith(`sensor.${DOMAIN}_`)),
        );

    const courierLabels = Object.fromEntries(
      COURIERS.map(([code, label]) => [code, this._courierLabel(label)]),
    );

    return ids
      .map((id) => this._withLastGood(states[id]))
      .filter(Boolean)
      .map((stateObj) => {
        const attrs = stateObj.attributes || {};
        const events = Array.isArray(attrs.events) ? attrs.events : [];
        const unavailable = stateObj.state === "unavailable" || stateObj.state === "unknown";
        // friendly_name is "<device name> <name>"; prefer the plain name
        let name = attrs.tracking_name || attrs.friendly_name || attrs.tracking_number || stateObj.entity_id;
        const deviceName = devices?.[entities?.[stateObj.entity_id]?.device_id]?.name;
        if (!attrs.tracking_name && deviceName && name.startsWith(`${deviceName} `)) {
          name = name.slice(deviceName.length + 1);
        }
        return {
          entityId: stateObj.entity_id,
          name,
          trackingNumber: attrs.tracking_number || "",
          ownerUserId: attrs.owner_user_id || "",
          ownerName: attrs.owner || "",
          courierName: attrs.courier && attrs.courier !== "unknown" ? courierLabels[attrs.courier] || attrs.courier_name || "" : "",
          state: stateObj.state,
          statusEn: attrs.status || "",
          statusEl: attrs.status_el || "",
          eta: parseEta(attrs.estimated_delivery),
          category: attrs.delivered ? "delivered" : attrs.status_category || "unknown",
          place: attrs.latest_place || "",
          when: parseWhen(attrs.latest_date, attrs.latest_time),
          events,
          unavailable,
        };
      })
      .filter((shipment) => this._config.show_delivered || shipment.category !== "delivered")
      .sort((a, b) => {
        const order = (CATEGORY_ORDER[a.category] ?? 2) - (CATEGORY_ORDER[b.category] ?? 2);
        if (order !== 0) return order;
        return (b.when?.key || "").localeCompare(a.when?.key || "");
      });
  }

  /** Keep showing the last known state while the integration (re)loads. */
  _withLastGood(stateObj) {
    if (!stateObj) return stateObj;
    const id = stateObj.entity_id;
    if (stateObj.state !== "unavailable" && stateObj.state !== "unknown") {
      this._lastGood.set(id, { stateObj, since: Date.now() });
      return stateObj;
    }
    const lastGood = this._lastGood.get(id);
    if (lastGood && Date.now() - lastGood.since < RELOAD_GRACE_MS) return lastGood.stateObj;
    return stateObj;
  }

  _statusText(shipment) {
    const t = this._t;
    if (shipment.unavailable) return t.unavailable;
    if (shipment.statusEn === "Not Found") return t.not_found;
    if (this._lang !== "el") return shipment.statusEn || shipment.state;
    // Greek UI: prefer the courier's own Greek text when there is one
    if (shipment.statusEl) return shipment.statusEl;
    const latest = shipment.events[0];
    if (latest && GREEK.test(latest.status || "")) return latest.status;
    return shipment.state;
  }

  _eventText(event) {
    if (this._lang === "el" && GREEK.test(event.status || "")) return event.status;
    return event.status_translated || event.status || "";
  }

  _update() {
    if (!this._hass) return;
    if (!this._built) this._build();

    // Pending rows disappear once their sensor exists (or after a timeout)
    const shipments = this._shipments();
    const known = new Set(shipments.map((shipment) => shipment.trackingNumber));
    for (const [number, pending] of this._pending) {
      if (known.has(number) || Date.now() - pending.since > PENDING_TIMEOUT_MS) {
        this._pending.delete(number);
      }
    }

    const signature = JSON.stringify([
      this._lang,
      shipments.map((s) => [s.entityId, this._hass.states[s.entityId]?.last_updated]),
      [...this._pending.keys()],
      [...this._expanded],
      this._armedRemove,
      this._editingOwner,
      this._people().map((person) => [person.entityId, person.name]),
    ]);
    if (signature === this._signature) return;
    this._signature = signature;
    this._renderList(shipments);
  }

  _build() {
    const t = this._t;
    const showForm = this._config.show_add_form !== false;
    const options = COURIERS.map(
      ([code, label]) => `<option value="${code}">${escapeHtml(this._courierLabel(label))}</option>`,
    ).join("");
    // New shipments belong to whoever adds them unless they pick someone else;
    // owners only matter when more than one person uses Home Assistant
    const people = this._people();
    const showOwners = people.length > 1;
    const me = people.find((person) => person.userId === this._hass.user?.id);
    const ownerOptions = this._ownerOptions(people, me ? me.entityId : "");

    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <ha-card>
        <div class="header">
          <div class="title"><ha-icon icon="mdi:package-variant-closed"></ha-icon><span>${escapeHtml(this._config.title || t.title)}</span></div>
          <span class="count"></span>
        </div>
        ${showForm ? `
          <form autocomplete="off"${showOwners ? ' class="with-owner"' : ""}>
            <input name="tracking_number" placeholder="${escapeHtml(t.tracking_number)}" aria-label="${escapeHtml(t.tracking_number)}" spellcheck="false" autocapitalize="characters">
            <input name="name" placeholder="${escapeHtml(t.name)}" aria-label="${escapeHtml(t.name)}">
            <select name="courier" aria-label="${escapeHtml(t.courier)}">${options}</select>
            ${showOwners ? `<select name="owner" aria-label="${escapeHtml(t.owner)}" title="${escapeHtml(t.owner)}">${ownerOptions}</select>` : ""}
            <button class="add" type="submit"><ha-icon icon="mdi:plus"></ha-icon><span>${escapeHtml(t.add)}</span></button>
          </form>
          <div class="msg" role="status"></div>` : ""}
        <div class="list"></div>
      </ha-card>`;

    const form = this.shadowRoot.querySelector("form");
    if (form) {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._add(form);
      });
      form.tracking_number.addEventListener("input", () => this._message(""));
    }
    const list = this.shadowRoot.querySelector(".list");
    list.addEventListener("click", (event) => this._onListClick(event));
    list.addEventListener("change", (event) => this._onOwnerChange(event));
    list.addEventListener("focusout", (event) => {
      // Leaving the owner dropdown without picking closes it
      if (!event.target.matches?.("select.owner-edit")) return;
      setTimeout(() => {
        if (this._editingOwner === event.target.dataset.id) {
          this._editingOwner = null;
          this._update();
        }
      }, 200);
    });
    this._built = true;
  }

  /** <option>s with the people and "shared"; values are person entities ("" = shared). */
  _ownerOptions(people, selected) {
    const options = people.map(
      (person) =>
        `<option value="${escapeHtml(person.entityId)}"${person.entityId === selected ? " selected" : ""}>${escapeHtml(person.name)}</option>`,
    );
    options.push(`<option value=""${selected ? "" : " selected"}>${escapeHtml(this._t.shared)}</option>`);
    return options.join("");
  }

  _message(text, isError = false) {
    const msg = this.shadowRoot.querySelector(".msg");
    if (!msg) return;
    msg.textContent = text;
    msg.classList.toggle("error", isError);
  }

  async _add(form) {
    const t = this._t;
    const trackingNumber = form.tracking_number.value.replace(/\s+/g, "").toUpperCase();
    const name = form.name.value.trim();
    const courier = form.courier.value;

    if (!trackingNumber) {
      this._message(t.required, true);
      form.tracking_number.focus();
      return;
    }
    if (this._shipments().some((s) => s.trackingNumber === trackingNumber) || this._pending.has(trackingNumber)) {
      this._message(t.exists, true);
      return;
    }

    const data = { tracking_number: trackingNumber, courier };
    if (name) data.name = name;
    if (form.owner) data.owner = form.owner.value;
    if (this._config.entry_id) data.config_entry_id = this._config.entry_id;

    const button = form.querySelector("button.add");
    button.disabled = true;
    try {
      await this._hass.callService(DOMAIN, "add_tracking", data);
      this._pending.set(trackingNumber, { name: name || trackingNumber, since: Date.now() });
      form.reset();
      this._message(t.added);
      this._update();
    } catch (err) {
      this._message(err?.message || String(err), true);
    } finally {
      button.disabled = false;
    }
  }

  async _onListClick(event) {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    const { action, id } = target.dataset;

    if (action === "toggle") {
      this._expanded.has(id) ? this._expanded.delete(id) : this._expanded.add(id);
      this._update();
    } else if (action === "more-info") {
      this.dispatchEvent(new CustomEvent("hass-more-info", {
        detail: { entityId: id }, bubbles: true, composed: true,
      }));
    } else if (action === "owner") {
      this._editingOwner = id;
      this._update();
      const select = this.shadowRoot.querySelector("select.owner-edit");
      select?.focus();
      try {
        select?.showPicker?.();
      } catch (err) {
        // Not supported: the focused dropdown opens on the next click
      }
    } else if (action === "remove") {
      // First click arms the button, second click removes
      if (this._armedRemove !== id) {
        this._armedRemove = id;
        clearTimeout(this._armTimer);
        this._armTimer = setTimeout(() => {
          this._armedRemove = null;
          this._update();
        }, 4000);
        this._update();
        return;
      }
      this._armedRemove = null;
      try {
        await this._hass.callService(DOMAIN, "remove_tracking", {
          tracking_number: id,
          ...(this._config.entry_id ? { config_entry_id: this._config.entry_id } : {}),
        });
      } catch (err) {
        this._message(err?.message || String(err), true);
      }
      this._update();
    }
  }

  async _onOwnerChange(event) {
    const select = event.target.closest("select.owner-edit");
    if (!select) return;
    this._editingOwner = null;
    try {
      await this._hass.callService(DOMAIN, "set_owner", {
        tracking_number: select.dataset.id,
        owner: select.value,
        ...(this._config.entry_id ? { config_entry_id: this._config.entry_id } : {}),
      });
    } catch (err) {
      this._message(err?.message || String(err), true);
    }
    this._update();
  }

  /** Owner tag of a row; a dropdown while it is being changed. */
  _ownerTag(shipment, people) {
    const t = this._t;
    if (people.length < 2 || !shipment.trackingNumber) return "";
    const person = people.find((p) => p.userId === shipment.ownerUserId);
    if (this._editingOwner === shipment.trackingNumber) {
      return `<select class="owner-edit" data-id="${escapeHtml(shipment.trackingNumber)}" aria-label="${escapeHtml(t.owner)}">${this._ownerOptions(people, person ? person.entityId : "")}</select>`;
    }
    const label = shipment.ownerUserId ? person?.name || shipment.ownerName || shipment.ownerUserId : t.shared;
    const icon = shipment.ownerUserId ? "mdi:account-outline" : "mdi:account-multiple-outline";
    return `<button class="link" data-action="owner" data-id="${escapeHtml(shipment.trackingNumber)}" title="${escapeHtml(t.change_owner)}"><ha-icon icon="${icon}"></ha-icon>${escapeHtml(label)}</button>`;
  }

  _bar(category, pending = false) {
    const steps = { created: 1, in_transit: 2, delivered: 3 }[category] || 0;
    const cls = category === "delivered" ? "done" : "on";
    return `<div class="bar${pending ? " pending" : ""}">${[1, 2, 3]
      .map((step) => `<i class="${step <= steps ? cls : ""}"></i>`)
      .join("")}</div>`;
  }

  _renderList(shipments) {
    const t = this._t;
    const list = this.shadowRoot.querySelector(".list");
    const people = this._people();
    const active = shipments.filter((s) => s.category !== "delivered").length + this._pending.size;
    this.shadowRoot.querySelector(".count").textContent = active ? t.active(active) : "";

    const pendingRows = [...this._pending].map(([number, pending]) => `
      <div class="row">
        <div class="head"><span class="name">${escapeHtml(pending.name)}</span></div>
        <div class="status muted">${escapeHtml(t.searching)}</div>
        ${this._bar("unknown", true)}
        <div class="meta"><div class="info"><span class="mono">${escapeHtml(number)}</span></div></div>
      </div>`);

    const rows = shipments.map((s) => {
      const delivered = s.category === "delivered";
      const expanded = this._expanded.has(s.entityId);
      const armed = this._armedRemove === s.trackingNumber;
      const badge = delivered
        ? `<span class="badge ok"><ha-icon icon="mdi:check"></ha-icon> ${escapeHtml(t.delivered)}</span>`
        : s.courierName ? `<span class="badge">${escapeHtml(s.courierName)}</span>` : "";
      const statusText = this._statusText(s);
      const muted = s.unavailable || s.statusEn === "Not Found";

      const info = [
        delivered && s.courierName ? `<span>${escapeHtml(s.courierName)}</span>` : "",
        s.place ? `<span><ha-icon icon="mdi:map-marker-outline"></ha-icon>${escapeHtml(s.place)}</span>` : "",
        s.when ? `<span><ha-icon icon="mdi:clock-outline"></ha-icon>${escapeHtml(s.when.label)}</span>` : "",
        !delivered && s.eta ? `<span><ha-icon icon="mdi:calendar-clock"></ha-icon>${escapeHtml(t.expected)} ${escapeHtml(s.eta.label)}</span>` : "",
        this._ownerTag(s, people),
        s.trackingNumber ? `<span class="mono">${escapeHtml(s.trackingNumber)}</span>` : "",
      ].filter(Boolean).join("");
      const actions = [
        s.events.length
          ? `<button class="link" data-action="toggle" data-id="${escapeHtml(s.entityId)}" aria-expanded="${expanded}">${escapeHtml(t.updates(s.events.length))}<ha-icon icon="mdi:chevron-${expanded ? "up" : "down"}"></ha-icon></button>`
          : "",
        s.trackingNumber
          ? `<button class="link remove${armed ? " armed" : ""}" data-action="remove" data-id="${escapeHtml(s.trackingNumber)}" title="${escapeHtml(t.remove)}">${armed ? `${escapeHtml(t.confirm_remove)} ` : ""}<ha-icon icon="mdi:delete${armed ? "" : "-outline"}"></ha-icon></button>`
          : "",
      ].filter(Boolean).join("");

      const timeline = expanded
        ? `<div class="timeline">${s.events.map((event) => {
            const when = parseWhen(event.date, event.time);
            const parts = [when ? `<span class="when">${escapeHtml(when.label)}</span>` : "", escapeHtml(this._eventText(event))];
            if (event.location) parts.push(`<span class="when">${escapeHtml(event.location)}</span>`);
            return `<div class="event">${parts.filter(Boolean).join(" · ")}</div>`;
          }).join("")}</div>`
        : "";

      return `
        <div class="row">
          <div class="head">
            <span class="name" data-action="more-info" data-id="${escapeHtml(s.entityId)}">${escapeHtml(s.name)}</span>
            ${badge}
          </div>
          ${delivered ? "" : `<div class="status${muted ? " muted" : ""}">${escapeHtml(statusText)}</div>`}
          ${this._bar(s.category)}
          <div class="meta"><div class="info">${info}</div><div class="actions">${actions}</div></div>
          ${timeline}
        </div>`;
    });

    const all = [...pendingRows, ...rows];
    list.innerHTML = all.length
      ? all.join("")
      : `<div class="empty">${escapeHtml(this._config.show_add_form !== false ? t.empty : t.empty_no_form)}</div>`;
  }
}

function registerCard() {
  if (customElements.get(CARD_TYPE)) return;
  try {
    customElements.define(CARD_TYPE, GreekCourierTrackerCard);
  } catch (err) {
    // The class is already registered elsewhere; register a fresh subclass
    customElements.define(CARD_TYPE, class extends GreekCourierTrackerCard {});
  }
}

registerCard();

// The Home Assistant frontend can replace window.customElements (scoped
// registry polyfill) while it starts. When this script loads first (for
// example from the browser cache) the card ends up in the old registry, so
// define it again until the frontend's root element exists.
const registerUntil = Date.now() + 60 * 1000;
const registerTimer = setInterval(() => {
  registerCard();
  if (customElements.get("home-assistant") || Date.now() > registerUntil) {
    clearInterval(registerTimer);
  }
}, 200);

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TYPE)) {
  window.customCards.push({
    type: CARD_TYPE,
    name: "Greek Courier Tracker",
    description: "Tracked shipments with progress, history and a quick add form.",
    preview: true,
    documentationURL: "https://github.com/thanasis00/greek-courier-tracker-hacs",
  });
}
