/**
 * What the visual test renders: every way a shipment can look in the card.
 *
 * The clock is fixed by run.py at NOW (Athens time), so "3 days ago" and
 * "Checked 11:48" come out the same on every run. Add a scenario (or a row to
 * one) whenever the card learns to show something new.
 */

// In a function: the card script already has top-level names such as DOMAIN
(() => {
const NOW = "2026-11-20T12:00:00+02:00";
const DOMAIN = "greek_courier_tracker";

/** Date and time strings of a moment some hours before NOW. */
function ago(hours) {
  const moment = new Date(new Date(NOW).getTime() - hours * 3600000);
  // The couriers give Athens times; the page runs in Europe/Athens
  const pad = (number) => String(number).padStart(2, "0");
  return {
    date: `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())}`,
    time: `${pad(moment.getHours())}:${pad(moment.getMinutes())}`,
  };
}

function event(hours, status, location = "ΑΘΗΝΑ", extra = {}) {
  return { ...ago(hours), location, status, status_translated: status, stage: null, problem: null, ...extra };
}

const CATEGORY = { created: "created", delivered: "delivered", undefined: "unknown", null: "unknown" };

/** The state of a tracking sensor, with the attributes the integration gives it. */
function sensor(number, options) {
  const {
    name = number,
    courier = "elta",
    courierName = "ELTA Courier",
    status = "Σε μεταφορά",
    statusEl = null,
    stage = "in_transit",
    problem = null,
    events = [event(20, status)],
    state = statusEl || status,
    owner = null,
    ...extra
  } = options;
  const latest = events[0] || {};
  return {
    entity_id: `sensor.${DOMAIN}_${number.toLowerCase()}`,
    state,
    last_updated: NOW,
    attributes: {
      tracking_number: number,
      tracking_name: name,
      owner_user_id: owner,
      owner: owner ? { u1: "Αθανάσιος", u2: "Μαρία" }[owner] : null,
      courier,
      courier_name: courierName,
      tracking_url: `https://example.com/track/${number}`,
      status,
      status_el: statusEl || status,
      status_category: CATEGORY[stage] || "in_transit",
      stage,
      problem,
      estimated_delivery: null,
      latest_date: latest.date || null,
      latest_time: latest.time || null,
      latest_place: latest.location || null,
      last_movement: null,
      stalled: false,
      events,
      delivered: stage === "delivered",
      stop_tracking_delivered: false,
      tracking_stopped: false,
      error_message: null,
      last_updated: new Date(new Date(NOW).getTime() - 12 * 60000).toISOString(),
      ...extra,
    },
  };
}

const PEOPLE = [
  { entity_id: "person.athanasios", state: "home", attributes: { user_id: "u1", friendly_name: "Αθανάσιος" } },
  { entity_id: "person.maria", state: "home", attributes: { user_id: "u2", friendly_name: "Μαρία" } },
];

// One row for each stage of the progress bar
const STAGES = [
  sensor("SE100000001GR", { name: "Δημιουργήθηκε", stage: "created", status: "Δημιουργία ΣΥ.ΔΕ.ΤΑ.", events: [event(30, "Δημιουργία ΣΥ.ΔΕ.ΤΑ.")] }),
  sensor("SE100000002GR", { name: "Σε μεταφορά", events: [event(5, "Άφιξη σε", "ΚΔ ΘΕΣΣΑΛΟΝΙΚΗΣ"), event(30, "Παραλαβή από αποστολέα")] }),
  sensor("SE100000003GR", { name: "Προς παράδοση", stage: "out_for_delivery", status: "Σε διανομέα προς παράδοση", events: [event(3, "Σε διανομέα προς παράδοση")] }),
  sensor("1234567890", { name: "Στο locker", courier: "box_now", courierName: "Box Now", stage: "ready_for_pickup", status: "At Destination Locker", events: [event(4, "in-final-destination", "Locker Κηφισιά")], estimated_delivery: "2026-11-21" }),
  sensor("SE100000005GR", { name: "Παραδόθηκε", stage: "delivered", status: "Αποστολή παραδόθηκε", events: [event(26, "Αποστολή παραδόθηκε")] }),
];

// One row for each problem
const PROBLEM_ROWS = [
  ["attempt_failed", "out_for_delivery", "Απουσία παραλήπτη - Επικοινωνία με το κατάστημα"],
  ["rerouted", "in_transit", "Επαναδρομολόγηση παράδοσης"],
  ["held", "in_transit", "Ελλιπής διεύθυνση"],
  ["returning", "in_transit", "Επιστροφή στον αποστολέα"],
  ["returned", "in_transit", "Επιστράφηκε στον αποστολέα"],
  ["cancelled", "created", "Cancelled"],
  ["expired", "ready_for_pickup", "Expired"],
];
const PROBLEMS = PROBLEM_ROWS.map(([problem, stage, status], index) =>
  sensor(`PR${String(index).padStart(8, "0")}GR`, {
    name: problem,
    stage,
    problem,
    status,
    events: [event(6 + index, status, "ΑΘΗΝΑ", { problem }), event(40, "Σε διανομέα προς παράδοση")],
  }),
);

// Everything else a row can show
const SPECIAL = [
  sensor("NF000000001GR", { name: "Δεν βρέθηκε ακόμα", courier: "unknown", courierName: "", stage: null, status: "Not Found", events: [] }),
  sensor("SE200000002GR", { name: "Μη διαθέσιμο", state: "unavailable" }),
  sensor("SE200000003GR", { name: "Χωρίς κίνηση", events: [event(100, "Άφιξη σε", "ΚΔ ΑΘΗΝΑΣ")], stalled: true }),
  sensor("E8GYRRONRYKL9", { name: "Με αναμενόμενη παράδοση", courier: "skroutz", courierName: "Skroutz Last Mile", status: "Η αποστολή βρίσκεται στο κέντρο διαλογής", events: [event(2, "Η αποστολή βρίσκεται στο κέντρο διαλογής", "SLM HUB Αιγάλεω")], estimated_delivery: "2026-11-21T10:00+02:00" }),
  sensor("SE200000005GR", { name: "Ένα πολύ μεγάλο όνομα αποστολής που δεν χωράει σε μία γραμμή της κάρτας" }),
  sensor("9826520605", { name: "ACS", courier: "acs", courierName: "ACS Courier", status: "Στο κέντρο διαλογής Αθήνα", events: [event(9, "Στο κέντρο διαλογής Αθήνα", ""), event(60, "Παραλαβή αποστολής", "")] }),
];

// Rows opened, with their timeline and the names of the steps
const EXPANDED = [
  STAGES[2],
  STAGES[3],
  PROBLEMS[0],
  sensor("SE300000004GR", { name: "Πολλές ενημερώσεις", events: [event(1, "Άφιξη σε", "ΚΔ ΘΕΣΣΑΛΟΝΙΚΗΣ"), event(20, "Αναχώρηση από", "ΚΔ ΑΘΗΝΑΣ"), event(30, "Άφιξη σε", "ΚΔ ΑΘΗΝΑΣ"), event(50, "Παραλαβή από αποστολέα", "ΠΕΙΡΑΙΑΣ")] }),
];

const OWNED = [
  sensor("SE400000001GR", { name: "Του Αθανάσιου", owner: "u1" }),
  sensor("SE400000002GR", { name: "Της Μαρίας", owner: "u2", stage: "out_for_delivery", status: "Σε διανομέα προς παράδοση" }),
  sensor("SE400000003GR", { name: "Κοινή" }),
];

// Removed shipments kept in the history (as shipment_history.snapshot stores them)
const KEPT = [STAGES[4], PROBLEMS[4]].map((stateObj, index) => ({
  ...stateObj.attributes,
  name: `Ιστορικό ${index + 1}`,
  removed_at: "2026-11-18T09:00:00+00:00",
}));

function states(...stateObjs) {
  return Object.fromEntries(stateObjs.flat().map((stateObj) => [stateObj.entity_id, stateObj]));
}

const NO_FORM = { show_add_form: false };

window.SCENARIOS = [
  { name: "overview", width: 520, config: {}, states: states(STAGES[1], STAGES[3], PROBLEMS[0], STAGES[4]) },
  { name: "overview-narrow", width: 340, config: {}, states: states(STAGES[1], STAGES[3], PROBLEMS[0], STAGES[4]) },
  { name: "stages", width: 520, config: NO_FORM, states: states(STAGES) },
  { name: "problems", width: 520, config: NO_FORM, states: states(PROBLEMS) },
  { name: "special", width: 520, config: NO_FORM, states: states(SPECIAL), pending: ["SE999999999GR"] },
  { name: "expanded", width: 520, config: NO_FORM, states: states(EXPANDED), expand: true },
  { name: "expanded-narrow", width: 340, config: NO_FORM, states: states(EXPANDED), expand: true },
  { name: "owners", width: 520, config: {}, states: states(OWNED, PEOPLE) },
  {
    name: "history",
    width: 520,
    config: NO_FORM,
    states: states(STAGES[1]),
    history: { shipments: KEPT, keep_history: true },
    historyOpen: true,
  },
  { name: "hide-delivered", width: 520, config: { ...NO_FORM, show_delivered: false }, states: states(STAGES) },
  { name: "empty", width: 520, config: {}, states: {} },
  { name: "empty-no-form", width: 520, config: NO_FORM, states: {} },
];

// Each scenario in both languages
window.SCENARIOS = window.SCENARIOS.flatMap((scenario) =>
  ["el", "en"].map((language) => ({ ...scenario, name: `${scenario.name}-${language}`, language })),
);

/** The parts of hass the card reads. */
window.fakeHass = (scenario) => ({
  states: scenario.states,
  language: scenario.language,
  locale: { language: scenario.language },
  entities: {},
  devices: {},
  user: { id: "u1", name: "Αθανάσιος" },
  callService: async () => {},
  callWS: async () => ({}),
  connection: {
    subscribeMessage: async (callback) => {
      callback(scenario.history || { shipments: [], keep_history: false });
      return () => {};
    },
  },
});
})();
