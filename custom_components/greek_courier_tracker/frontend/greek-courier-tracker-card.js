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
 *   show_history: true        # optional, default true: removed shipments kept
 *                             # by the integration (Configure → Settings)
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
    move_to_history: "Move to the history",
    confirm_move: "To the history?",
    history: (count) => `History (${count})`,
    removed_on: (date) => `Removed ${date}`,
    delete_forever: "Delete from the history",
    confirm_delete: "Delete for good?",
    delivered: "Delivered",
    not_found: "Not found yet",
    unavailable: "Unavailable",
    expected: "Expected",
    copy: "Copy tracking number",
    copied: "Tracking number copied",
    copy_failed: "Couldn't copy the tracking number",
    open_site: (courier) => `Track on the ${courier || "courier's"} website`,
    stages: {
      created: "Created",
      in_transit: "In transit",
      out_for_delivery: "Out for delivery",
      ready_for_pickup: "Ready for pickup",
      delivered: "Delivered",
    },
    last_mile: "Delivery",
    problems: {
      attempt_failed: "Delivery attempt failed",
      rerouted: "Delivery changed",
      held: "On hold",
      returning: "Returning to sender",
      returned: "Returned to sender",
      cancelled: "Cancelled",
      expired: "Not collected in time",
    },
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
    move_to_history: "Μεταφορά στο ιστορικό",
    confirm_move: "Στο ιστορικό;",
    history: (count) => `Ιστορικό (${count})`,
    removed_on: (date) => `Αφαιρέθηκε ${date}`,
    delete_forever: "Διαγραφή από το ιστορικό",
    confirm_delete: "Οριστική διαγραφή;",
    delivered: "Παραδόθηκε",
    not_found: "Δεν βρέθηκε ακόμα",
    unavailable: "Μη διαθέσιμο",
    expected: "Αναμένεται",
    copy: "Αντιγραφή αριθμού",
    copied: "Ο αριθμός αντιγράφηκε",
    copy_failed: "Δεν ήταν δυνατή η αντιγραφή",
    open_site: (courier) => `Παρακολούθηση στη σελίδα της εταιρείας${courier ? ` (${courier})` : ""}`,
    stages: {
      created: "Δημιουργήθηκε",
      in_transit: "Σε μεταφορά",
      out_for_delivery: "Προς παράδοση",
      ready_for_pickup: "Για παραλαβή",
      delivered: "Παραδόθηκε",
    },
    last_mile: "Παράδοση",
    problems: {
      attempt_failed: "Αποτυχημένη απόπειρα παράδοσης",
      rerouted: "Αλλαγή παράδοσης",
      held: "Σε αναμονή",
      returning: "Επιστρέφει στον αποστολέα",
      returned: "Επιστράφηκε στον αποστολέα",
      cancelled: "Ακυρώθηκε",
      expired: "Δεν παραλήφθηκε εγκαίρως",
    },
  },
};

const CATEGORY_ORDER = { in_transit: 0, created: 1, unknown: 2, error: 2, delivered: 3 };
// Progress bar: the last mile is either to the door or to a locker/store (step 3)
const STAGE_STEPS = { created: 1, in_transit: 2, out_for_delivery: 3, ready_for_pickup: 3, delivered: 4 };
const BAR_STEPS = 4;
// Problems that end the trip are shown in red, the others in orange
const FINAL_PROBLEMS = new Set(["returning", "returned", "cancelled", "expired"]);
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
  .bar i.warn { background: var(--warning-color, #ffa600); }
  .bar i.bad { background: var(--error-color, #db4437); }
  .bar.pending i { animation: pulse 1.4s ease-in-out infinite; }
  .steps { display: flex; gap: 4px; margin-top: 4px; font-size: 11px; color: var(--secondary-text-color); }
  .steps span { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .steps span.current { color: var(--primary-text-color); font-weight: 500; }
  .chip.warn { color: var(--warning-color, #ffa600); }
  .chip.bad { color: var(--error-color, #db4437); }
  .event.problem { color: var(--warning-color, #ffa600); }
  .event.problem.bad { color: var(--error-color, #db4437); }
  @keyframes pulse { 50% { opacity: 0.35; } }
  .details, .foot { display: flex; align-items: center; gap: 4px 14px; margin-top: 8px; font-size: 13px; line-height: 20px; color: var(--secondary-text-color); }
  .details { flex-wrap: wrap; }
  .foot { align-items: flex-start; justify-content: space-between; gap: 4px 12px; }
  .ids { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 14px; min-width: 0; }
  .actions { flex: none; display: flex; align-items: center; gap: 12px; }
  .chip { display: inline-flex; align-items: center; gap: 4px; min-width: 0; max-width: 100%; }
  .chip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .details ha-icon, .foot ha-icon { --mdc-icon-size: 16px; flex: none; }
  .number { display: inline-flex; align-items: center; gap: 8px; }
  .number ha-icon { --mdc-icon-size: 14px; }
  .mono, button.link.mono { font-family: var(--code-font-family, ui-monospace, monospace); }
  button.link, a.link { font: inherit; font-size: 13px; color: inherit; background: none; border: none; padding: 0; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; text-decoration: none; }
  button.link:hover, a.link:hover { color: var(--primary-text-color); }
  button.remove.armed { color: var(--error-color); }
  select.owner-edit { width: auto; height: 28px; font-size: 13px; padding: 0 6px; }
  .timeline { margin: 10px 0 0 6px; padding-left: 14px; border-left: 2px solid var(--divider-color); font-size: 13px; color: var(--primary-text-color); }
  .event { margin-bottom: 8px; }
  .event:last-child { margin-bottom: 0; }
  .event .when { color: var(--secondary-text-color); }
  .empty { border-top: 1px solid var(--divider-color); padding: 14px 0 2px; font-size: 14px; color: var(--secondary-text-color); }
  button.history-toggle { font: inherit; font-size: 14px; width: 100%; display: flex; align-items: center; gap: 8px; padding: 12px 0 4px; margin: 0; border: none; border-top: 1px solid var(--divider-color); background: none; color: var(--secondary-text-color); cursor: pointer; text-align: left; }
  button.history-toggle:hover { color: var(--primary-text-color); }
  button.history-toggle span { flex: 1; }
  button.history-toggle ha-icon { --mdc-icon-size: 18px; }
  .kept .row .name { cursor: default; }
  .kept .bar i.on, .kept .bar i.done, .kept .bar i.warn, .kept .bar i.bad { opacity: 0.6; }
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

/** A UTC timestamp (when a shipment was removed) -> local date label. */
function parseRemoved(value) {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) return null;
  const pad = (number) => String(number).padStart(2, "0");
  return parseWhen(`${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`, "");
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
    // Removed shipments kept by the integration, from its websocket subscription
    this._history = { shipments: [], keepHistory: false, version: 0 };
    this._historyOpen = false;
    this._unsubHistory = null;
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = { show_add_form: true, show_delivered: true, show_history: true, ...(config || {}) };
    this._built = false;
    this._signature = "";
    if (this._hass) this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._subscribeHistory();
    this._update();
  }

  connectedCallback() {
    if (this._hass) this._subscribeHistory();
  }

  disconnectedCallback() {
    const unsub = this._unsubHistory;
    this._unsubHistory = null;
    if (typeof unsub === "function") Promise.resolve(unsub()).catch(() => {});
  }

  /** Follow the history; it also says whether removing keeps a shipment. */
  async _subscribeHistory() {
    if (this._unsubHistory || this._subscribing || this._historyUnsupported || !this._hass?.connection) return;
    this._subscribing = true;
    try {
      const unsub = await this._hass.connection.subscribeMessage(
        (message) => {
          this._history = {
            shipments: Array.isArray(message?.shipments) ? message.shipments : [],
            keepHistory: Boolean(message?.keep_history),
            version: this._history.version + 1,
          };
          this._update();
        },
        { type: `${DOMAIN}/history/subscribe` },
      );
      if (this.isConnected) {
        this._unsubHistory = unsub;
      } else {
        Promise.resolve(unsub()).catch(() => {});
      }
    } catch (err) {
      // An older version of the integration, without the history
      this._historyUnsupported = true;
    } finally {
      this._subscribing = false;
    }
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

    return ids
      .map((id) => this._withLastGood(states[id]))
      .filter(Boolean)
      .map((stateObj) => {
        const attrs = stateObj.attributes || {};
        // friendly_name is "<device name> <name>"; prefer the plain name
        let name = attrs.tracking_name || attrs.friendly_name || attrs.tracking_number || stateObj.entity_id;
        const deviceName = devices?.[entities?.[stateObj.entity_id]?.device_id]?.name;
        if (!attrs.tracking_name && deviceName && name.startsWith(`${deviceName} `)) {
          name = name.slice(deviceName.length + 1);
        }
        return this._shipment(attrs, {
          entityId: stateObj.entity_id,
          name,
          state: stateObj.state,
          unavailable: stateObj.state === "unavailable" || stateObj.state === "unknown",
        });
      })
      .filter((shipment) => this._config.show_delivered || shipment.category !== "delivered")
      .sort((a, b) => {
        // Shipments with a problem first: they may need something from you
        const rank = (s) => (s.problem && s.category !== "delivered" ? -1 : CATEGORY_ORDER[s.category] ?? 2);
        const order = rank(a) - rank(b);
        if (order !== 0) return order;
        return (b.when?.key || "").localeCompare(a.when?.key || "");
      });
  }

  /** A shipment object from the attributes of a sensor, or of a kept shipment. */
  _shipment(attrs, extra) {
    const courierLabels = Object.fromEntries(
      COURIERS.map(([code, label]) => [code, this._courierLabel(label)]),
    );
    return {
      trackingNumber: attrs.tracking_number || "",
      // Only links to the courier websites, never other schemes
      trackingUrl: /^https?:\/\//.test(attrs.tracking_url || "") ? attrs.tracking_url : "",
      ownerUserId: attrs.owner_user_id || "",
      ownerName: attrs.owner || "",
      courierName: attrs.courier && attrs.courier !== "unknown" ? courierLabels[attrs.courier] || attrs.courier_name || "" : "",
      statusEn: attrs.status || "",
      statusEl: attrs.status_el || "",
      eta: parseEta(attrs.estimated_delivery),
      category: attrs.delivered ? "delivered" : attrs.status_category || "unknown",
      // Shipments kept by older versions have no stage: use the category
      stage: attrs.stage || (attrs.delivered ? "delivered" : STAGE_STEPS[attrs.status_category] ? attrs.status_category : null),
      problem: attrs.problem || null,
      place: attrs.latest_place || "",
      when: parseWhen(attrs.latest_date, attrs.latest_time),
      events: Array.isArray(attrs.events) ? attrs.events : [],
      ...extra,
    };
  }

  /** Removed shipments that the integration keeps, frozen, most recent first. */
  _keptShipments() {
    if (this._config.show_history === false) return [];
    return this._history.shipments.map((item) =>
      this._shipment(item, {
        // Keys of the expanded rows; kept rows have no sensor
        entityId: `history:${item.tracking_number}`,
        name: item.name || item.tracking_number || "",
        state: item.status || "",
        unavailable: false,
        removed: parseRemoved(item.removed_at),
        kept: true,
      }),
    );
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
      this._history.version,
      this._historyOpen,
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
    } else if (action === "copy") {
      this._copy(target);
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
    } else if (action === "history") {
      this._historyOpen = !this._historyOpen;
      this._update();
    } else if (action === "remove") {
      if (this._arm(id)) return;
      // The integration finds the entry that tracks the number (and keeps it in
      // the history if it is set to)
      await this._call("remove_tracking", { tracking_number: id });
    } else if (action === "delete-history") {
      if (this._arm(`history:${id}`)) return;
      await this._call("delete_history", { tracking_number: id });
    }
  }

  /** First click arms a remove button; returns false on the second (confirming) click. */
  _arm(key) {
    clearTimeout(this._armTimer);
    if (this._armedRemove === key) {
      this._armedRemove = null;
      return false;
    }
    this._armedRemove = key;
    this._armTimer = setTimeout(() => {
      this._armedRemove = null;
      this._update();
    }, 4000);
    this._update();
    return true;
  }

  async _call(service, data) {
    try {
      await this._hass.callService(DOMAIN, service, data);
    } catch (err) {
      this._message(err?.message || String(err), true);
    }
    this._update();
  }

  async _copy(button) {
    const t = this._t;
    let copied;
    try {
      await navigator.clipboard.writeText(button.dataset.id);
      copied = true;
    } catch (err) {
      // No clipboard API on plain http (local network), or no permission
      copied = this._copyWithSelection(button.dataset.id);
    }
    if (!copied) {
      this._toast(t.copy_failed);
      return;
    }
    this._toast(t.copied);
    const icon = button.querySelector("ha-icon");
    icon?.setAttribute("icon", "mdi:check");
    setTimeout(() => icon?.setAttribute("icon", "mdi:content-copy"), 1500);
  }

  /** Copy the old way, through a selected (invisible) text field. */
  _copyWithSelection(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.cssText = "position: fixed; top: 0; left: 0; opacity: 0;";
    document.body.appendChild(area);
    area.focus();
    area.select();
    try {
      return document.execCommand("copy");
    } catch (err) {
      return false;
    } finally {
      area.remove();
    }
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", {
      detail: { message }, bubbles: true, composed: true,
    }));
  }

  async _onOwnerChange(event) {
    const select = event.target.closest("select.owner-edit");
    if (!select) return;
    this._editingOwner = null;
    try {
      await this._hass.callService(DOMAIN, "set_owner", {
        tracking_number: select.dataset.id,
        owner: select.value,
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

  /** Tracking number that copies itself, with a link to the courier's own page. */
  _numberTag(number, url = "", courierName = "") {
    const t = this._t;
    const copy = `<button class="link mono" data-action="copy" data-id="${escapeHtml(number)}" title="${escapeHtml(t.copy)}">${escapeHtml(number)}<ha-icon icon="mdi:content-copy"></ha-icon></button>`;
    const open = url
      ? `<a class="link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(t.open_site(courierName))}" aria-label="${escapeHtml(t.open_site(courierName))}"><ha-icon icon="mdi:open-in-new"></ha-icon></a>`
      : "";
    return `<span class="number">${copy}${open}</span>`;
  }

  /** Progress bar in 4 steps; a problem colours the step the shipment is at. */
  _bar(stage, problem = null, pending = false) {
    const t = this._t;
    const reached = STAGE_STEPS[stage] || 0;
    const final = FINAL_PROBLEMS.has(problem);
    const cls = (step) => {
      if (step > reached) return "";
      if (stage === "delivered") return "done";
      if (final) return "bad";
      return problem && step === reached ? "warn" : "on";
    };
    const label = [t.stages[stage], t.problems[problem]].filter(Boolean).join(" · ");
    const aria = label ? ` role="img" aria-label="${escapeHtml(`${label} (${reached}/${BAR_STEPS})`)}" title="${escapeHtml(label)}"` : "";
    return `<div class="bar${pending ? " pending" : ""}"${aria}>${Array.from({ length: BAR_STEPS }, (_, index) =>
      `<i class="${cls(index + 1)}"></i>`).join("")}</div>`;
  }

  /** Names of the steps under the bar; the third is the door or the locker/store. */
  _stepLabels(stage) {
    const t = this._t;
    const reached = STAGE_STEPS[stage] || 0;
    const lastMile = stage === "out_for_delivery" || stage === "ready_for_pickup" ? t.stages[stage] : t.last_mile;
    const names = [t.stages.created, t.stages.in_transit, lastMile, t.stages.delivered];
    return `<div class="steps" aria-hidden="true">${names
      .map((name, index) => `<span class="${index + 1 === reached ? "current" : ""}">${escapeHtml(name)}</span>`)
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
        ${this._bar(null, null, true)}
        <div class="foot"><div class="ids">${this._numberTag(number)}</div></div>
      </div>`);

    const rows = shipments.map((s) => this._row(s, people));
    const all = [...pendingRows, ...rows];
    list.innerHTML = (all.length
      ? all.join("")
      : `<div class="empty">${escapeHtml(this._config.show_add_form !== false ? t.empty : t.empty_no_form)}</div>`)
      + this._historyBlock(people);
  }

  /** The collapsible list of removed shipments the integration keeps. */
  _historyBlock(people) {
    const kept = this._keptShipments();
    if (!kept.length) return "";
    const open = this._historyOpen;
    return `
      <button class="history-toggle" data-action="history" aria-expanded="${open}">
        <ha-icon icon="mdi:archive-outline"></ha-icon><span>${escapeHtml(this._t.history(kept.length))}</span><ha-icon icon="mdi:chevron-${open ? "up" : "down"}"></ha-icon>
      </button>
      ${open ? `<div class="kept">${kept.map((s) => this._row(s, people)).join("")}</div>` : ""}`;
  }

  /** Remove button of a tracked shipment; with the history on, it moves the shipment there. */
  _removeButton(s) {
    const t = this._t;
    const armed = this._armedRemove === s.trackingNumber;
    // Like the integration, numbers that no courier found aren't kept
    const keeps = this._history.keepHistory && !s.unavailable && s.statusEn !== "Not Found" && s.statusEn !== "Error";
    const [title, confirm, icon] = keeps
      ? [t.move_to_history, t.confirm_move, "mdi:archive-arrow-down"]
      : [t.remove, t.confirm_remove, "mdi:delete"];
    return `<button class="link remove${armed ? " armed" : ""}" data-action="remove" data-id="${escapeHtml(s.trackingNumber)}" title="${escapeHtml(title)}">${armed ? `${escapeHtml(confirm)} ` : ""}<ha-icon icon="${icon}${armed ? "" : "-outline"}"></ha-icon></button>`;
  }

  /** Delete button of a kept shipment. */
  _deleteButton(s) {
    const t = this._t;
    const armed = this._armedRemove === `history:${s.trackingNumber}`;
    return `<button class="link remove${armed ? " armed" : ""}" data-action="delete-history" data-id="${escapeHtml(s.trackingNumber)}" title="${escapeHtml(t.delete_forever)}">${armed ? `${escapeHtml(t.confirm_delete)} ` : ""}<ha-icon icon="mdi:delete${armed ? "" : "-outline"}"></ha-icon></button>`;
  }

  /** Owner of a kept shipment, as text (it can't change any more). */
  _keptOwnerTag(s, people) {
    if (people.length < 2) return "";
    const person = people.find((p) => p.userId === s.ownerUserId);
    const label = s.ownerUserId ? person?.name || s.ownerUserId : this._t.shared;
    const icon = s.ownerUserId ? "mdi:account-outline" : "mdi:account-multiple-outline";
    return `<span class="chip"><ha-icon icon="${icon}"></ha-icon><span>${escapeHtml(label)}</span></span>`;
  }

  /** One shipment: tracked (from its sensor) or kept in the history (s.kept). */
  _row(s, people) {
    const t = this._t;
    const delivered = s.category === "delivered";
    const expanded = this._expanded.has(s.entityId);
    const badge = delivered
      ? `<span class="badge ok"><ha-icon icon="mdi:check"></ha-icon> ${escapeHtml(t.delivered)}</span>`
      : s.courierName ? `<span class="badge">${escapeHtml(s.courierName)}</span>` : "";
    const statusText = this._statusText(s);
    const muted = s.unavailable || s.statusEn === "Not Found";

    const chip = (icon, text) =>
      `<span class="chip" title="${escapeHtml(text)}"><ha-icon icon="${icon}"></ha-icon><span>${escapeHtml(text)}</span></span>`;
    const problemText = !delivered && s.problem ? t.problems[s.problem] : "";
    const problemChip = problemText
      ? `<span class="chip ${FINAL_PROBLEMS.has(s.problem) ? "bad" : "warn"}" title="${escapeHtml(problemText)}"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><span>${escapeHtml(problemText)}</span></span>`
      : "";
    const details = [
      problemChip,
      delivered && s.courierName ? chip("mdi:truck-outline", s.courierName) : "",
      s.place ? chip("mdi:map-marker-outline", s.place) : "",
      s.when ? chip("mdi:clock-outline", s.when.label) : "",
      !delivered && !s.kept && s.eta ? chip("mdi:calendar-clock", `${t.expected} ${s.eta.label}`) : "",
      s.kept && s.removed ? chip("mdi:archive-outline", t.removed_on(s.removed.label)) : "",
    ].filter(Boolean).join("");
    const ids = [
      s.trackingNumber ? this._numberTag(s.trackingNumber, s.trackingUrl, s.courierName) : "",
      s.kept ? this._keptOwnerTag(s, people) : this._ownerTag(s, people),
    ].filter(Boolean).join("");
    const actions = [
      s.events.length
        ? `<button class="link" data-action="toggle" data-id="${escapeHtml(s.entityId)}" aria-expanded="${expanded}">${escapeHtml(t.updates(s.events.length))}<ha-icon icon="mdi:chevron-${expanded ? "up" : "down"}"></ha-icon></button>`
        : "",
      s.trackingNumber ? (s.kept ? this._deleteButton(s) : this._removeButton(s)) : "",
    ].filter(Boolean).join("");

    const timeline = expanded
      ? `<div class="timeline">${s.events.map((event) => {
          const when = parseWhen(event.date, event.time);
          const parts = [when ? `<span class="when">${escapeHtml(when.label)}</span>` : "", escapeHtml(this._eventText(event))];
          if (event.location) parts.push(`<span class="when">${escapeHtml(event.location)}</span>`);
          const problem = event.problem ? ` problem${FINAL_PROBLEMS.has(event.problem) ? " bad" : ""}` : "";
          return `<div class="event${problem}">${parts.filter(Boolean).join(" · ")}</div>`;
        }).join("")}</div>`
      : "";

    // Kept shipments have no sensor, so no more-info dialog
    const name = s.kept
      ? `<span class="name">${escapeHtml(s.name)}</span>`
      : `<span class="name" data-action="more-info" data-id="${escapeHtml(s.entityId)}">${escapeHtml(s.name)}</span>`;
    return `
      <div class="row">
        <div class="head">
          ${name}
          ${badge}
        </div>
        ${delivered ? "" : `<div class="status${muted ? " muted" : ""}">${escapeHtml(statusText)}</div>`}
        ${this._bar(s.stage, delivered ? null : s.problem)}
        ${expanded ? this._stepLabels(s.stage) : ""}
        ${details ? `<div class="details">${details}</div>` : ""}
        <div class="foot"><div class="ids">${ids}</div><div class="actions">${actions}</div></div>
        ${timeline}
      </div>`;
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
