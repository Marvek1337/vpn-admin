export const parseFree = (out: string) => {
  const line = out.split('\n').find((x) => x.startsWith('Mem:')) || '';
  const parts = line.trim().split(/\s+/);
  return { total: Number(parts[1] || 0), used: Number(parts[2] || 0) };
};
