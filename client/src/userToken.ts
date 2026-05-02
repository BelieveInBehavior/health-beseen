const STORAGE_KEY = "health_beseen_user_token";
const PARENT_SESSION_KEY = "health_beseen_parent_session_id";

export function getUserToken(): string {
  let token = localStorage.getItem(STORAGE_KEY);
  if (!token) {
    token = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, token);
  }
  return token;
}

export function getParentSessionId(): string {
  let parentId = localStorage.getItem(PARENT_SESSION_KEY);
  if (!parentId) {
    parentId = "admin";
    localStorage.setItem(PARENT_SESSION_KEY, parentId);
  }
  return parentId;
}
