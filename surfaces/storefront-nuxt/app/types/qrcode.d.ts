// Tipagem mínima do `qrcode` (o pacote não embarca tipos próprios). Só o que o
// WhatsappVerifyPanel usa: desenhar o deep link num <canvas> no cliente.
declare module 'qrcode' {
  interface ToCanvasOptions {
    width?: number
    margin?: number
    [key: string]: unknown
  }
  export function toCanvas (
    canvas: HTMLCanvasElement,
    text: string,
    options?: ToCanvasOptions
  ): Promise<void>
}
