export const sanitize = (data: Record<string, unknown>) => {
  const blocked = ['password', 'sshPassword', 'wgEasyPassword', 'token'];
  return Object.fromEntries(Object.entries(data).map(([k, v]) => [k, blocked.includes(k) ? '***' : v]));
};
