/** 全局只允许一个执行详情弹窗，避免多流水线同时自动弹出叠层。 */
let open = false;

export function isExecutionModalOpen(): boolean {
  return open;
}

export function markExecutionModalOpen(value: boolean): void {
  open = value;
}
