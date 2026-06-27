import { toPng } from 'html-to-image'
import { jsPDF } from 'jspdf'

/**
 * 导出 DOM 元素为 PNG 图片并触发下载
 *
 * @param element 要截图的 DOM 元素（通常是 ItineraryPrintView 的 root）
 * @param filename 不含扩展名的文件名，如 "北京-3天行程-202607221430"
 */
export async function exportAsImage(element: HTMLElement, filename: string): Promise<void> {
  const dataUrl = await toPng(element, {
    pixelRatio: 2,
    cacheBust: true,
    backgroundColor: '#ffffff',
  })
  triggerDownload(dataUrl, `${filename}.png`)
}

function triggerDownload(dataUrl: string, filename: string): void {
  const link = document.createElement('a')
  link.download = filename
  link.href = dataUrl
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

/**
 * 导出 DOM 元素为多页 A4 PDF
 *
 * 流程:
 * 1. html-to-image 把 DOM 渲染为 PNG dataURL（中文正常，避开 jsPDF 字体问题）
 * 2. 按 A4 比例 (595×842pt) 计算图片缩放
 * 3. 按 A4 高度切多页，jsPDF.addImage() + addPage()
 *
 * @param element 要导出的 DOM 元素
 * @param filename 不含扩展名的文件名
 */
export async function exportAsPdf(element: HTMLElement, filename: string): Promise<void> {
  const pngDataUrl = await toPng(element, {
    pixelRatio: 2,
    cacheBust: true,
    backgroundColor: '#ffffff',
  })

  const img = await loadImage(pngDataUrl)
  const imgWidth = img.width
  const imgHeight = img.height

  const pdfWidth = 595
  const pdfHeight = 842
  const margin = 20
  const usableWidth = pdfWidth - margin * 2
  const usableHeight = pdfHeight - margin * 2

  const scale = usableWidth / imgWidth
  const scaledHeight = imgHeight * scale

  const pdf = new jsPDF({ unit: 'pt', format: 'a4', orientation: 'portrait' })

  let remainingHeight = scaledHeight
  let srcY = 0

  while (remainingHeight > 0) {
    const chunkHeight = Math.min(usableHeight, remainingHeight)

    const canvas = document.createElement('canvas')
    canvas.width = imgWidth
    canvas.height = Math.ceil(chunkHeight / scale)
    const ctx = canvas.getContext('2d')!
    ctx.drawImage(
      img,
      0, srcY,
      imgWidth, canvas.height,
      0, 0,
      imgWidth, canvas.height
    )
    const chunkDataUrl = canvas.toDataURL('image/png')

    pdf.addImage(
      chunkDataUrl,
      'PNG',
      margin, margin,
      usableWidth, chunkHeight
    )

    srcY += canvas.height
    remainingHeight -= usableHeight
    if (remainingHeight > 0) {
      pdf.addPage()
    }
  }

  pdf.save(`${filename}.pdf`)
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })
}

/**
 * 用浏览器原生打印对话框打印行程
 *
 * 流程:
 * 1. 打开新窗口
 * 2. 写入元素的 outerHTML + 打印样式
 * 3. 等图片加载完触发 print()
 * 4. 关闭窗口
 *
 * @param element 要打印的 DOM 元素
 * @param title 打印窗口标题（也用作 document.title，影响 PDF 默认文件名）
 */
export function printItinerary(element: HTMLElement, title: string): void {
  const printWin = window.open('', '_blank', 'width=800,height=600')
  if (!printWin) {
    throw new Error('弹出窗口被浏览器拦截，请允许弹出窗口后重试')
  }

  printWin.document.write(`<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>${escapeHtml(title)}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Helvetica Neue', sans-serif; padding: 20px; color: #333; }
  @page { margin: 15mm; }
  @media print {
    body { padding: 0; }
  }
</style>
</head>
<body>${element.outerHTML}</body>
</html>`)
  printWin.document.close()

  printWin.onload = () => {
    setTimeout(() => {
      printWin.focus()
      printWin.print()
      setTimeout(() => printWin.close(), 100)
    }, 300)
  }
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * 生成行程导出文件名
 * @example "北京-3天行程-202607221430"
 */
export function buildExportFilename(city: string, days: number): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}`
  return `${city}-${days}天行程-${ts}`
}
