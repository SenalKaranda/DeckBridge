/**
 * TypeScript mirrors of the Pydantic schema in `src/deckbridge/storage/schema.py`.
 *
 * Keep these in lockstep with the Python definitions. The OpenAPI schema at
 * `/api/openapi.json` is the canonical source if there's a discrepancy.
 */

// ---- Press actions (discriminated union by `type`) -----------------------

export interface MQTTPublishAction {
  type: 'mqtt_publish';
  topic: string;
  payload: string;
  retain: boolean;
  qos: 0 | 1 | 2;
}

export interface HTTPWebhookAction {
  type: 'http_webhook';
  url: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  headers: Record<string, string>;
  body: string;
}

export interface PageSwitchAction {
  type: 'page_switch';
  target_page_id: string;
}

export interface NoOpAction {
  type: 'no_op';
}

export type PressAction =
  | MQTTPublishAction
  | HTTPWebhookAction
  | PageSwitchAction
  | NoOpAction;

export type PressActionType = PressAction['type'];

// ---- State subscription ---------------------------------------------------

export interface StateSubscription {
  topic: string;
  jmespath: string | null;
  icon_map: Record<string, string>;
  default_icon_id: string | null;
}

// ---- Entities -------------------------------------------------------------

export interface Page {
  id: string;
  deck_serial: string;
  name: string;
  order: number;
}

export interface Key {
  page_id: string;
  slot: number;
  label: string;
  icon_id: string | null;
  press: PressAction;
  state: StateSubscription | null;
  /** Extra inset in pixels added to all four sides of the key's content
   * region. 0 = renderer defaults; 1-20 progressively shrinks the icon
   * and pulls the label inward. Useful when an icon feels cropped. */
  padding: number;
  /** When false, painter skips drawing the icon (label is centered). */
  show_icon: boolean;
  /** When false, painter skips drawing the label even if non-empty. */
  show_label: boolean;
  /** Solid background color `#RRGGBB`, drawn under everything. */
  bg_color: string;
  /** Optional background image (icon-library id), cover-fitted under the icon. */
  bg_image_id: string | null;
  /** Label text color `#RRGGBB`. */
  label_color: string;
  /** Optional tint applied to the icon (multiply); null = no tint. */
  icon_color: string | null;
  /** Label font size in pixels (8-32). Default 14 matches v1.0.x. */
  font_size: number;
}

export interface Icon {
  id: string;
  name: string;
  source: 'bundled' | 'uploaded';
  reference: string;
  sha256: string | null;
}

// ---- Request / response bodies -------------------------------------------

export interface CreatePageBody {
  deck_serial: string;
  name?: string;
  order?: number;
}

export interface PatchPageBody {
  name?: string;
  order?: number;
  deck_serial?: string;
}

export interface KeyBody {
  label?: string;
  icon_id?: string | null;
  press?: PressAction;
  state?: StateSubscription | null;
  padding?: number;
  show_icon?: boolean;
  show_label?: boolean;
  bg_color?: string;
  bg_image_id?: string | null;
  label_color?: string;
  icon_color?: string | null;
  font_size?: number;
}

export interface StatusResponse {
  version: string;
  decks: { serial: string; model: string }[];
  broker_connected: boolean;
}

// ---- Defaults -------------------------------------------------------------

export function defaultPressAction(): PressAction {
  return { type: 'no_op' };
}

export function defaultStateSubscription(): StateSubscription {
  return { topic: '', jmespath: null, icon_map: {}, default_icon_id: null };
}

export function emptyKey(page_id: string, slot: number): Key {
  return {
    page_id,
    slot,
    label: '',
    icon_id: null,
    press: defaultPressAction(),
    state: null,
    padding: 0,
    show_icon: true,
    show_label: true,
    bg_color: '#000000',
    bg_image_id: null,
    label_color: '#FFFFFF',
    icon_color: null,
    font_size: 14,
  };
}
