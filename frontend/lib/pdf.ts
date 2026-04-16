/**
 * Markdown → PDF export.
 *
 * Captures a rendered HTML element, applies print-friendly styles
 * (white background, dark text), and downloads as a PDF using
 * html2canvas + jsPDF.
 *
 * Dynamic imports keep both libraries out of the initial bundle.
 */

export async function exportElementToPdf(
  element: HTMLElement,
  filename = 'export.pdf',
): Promise<void> {
  const [{ default: html2canvas }, { default: jsPDF }] = await Promise.all([
    import('html2canvas'),
    import('jspdf'),
  ])

  // Clone the element so we can restyle for PDF without affecting the UI
  const clone = element.cloneNode(true) as HTMLElement
  clone.style.cssText = [
    'position:fixed',
    'top:-9999px',
    'left:-9999px',
    'width:720px',          // A4-ish content width in px
    'padding:40px',
    'background:#ffffff',
    'color:#111111',
    'font-family:Georgia,serif',
    'font-size:14px',
    'line-height:1.6',
  ].join(';')

  // Override dark-theme child styles for PDF readability
  const style = document.createElement('style')
  style.textContent = `
    * { color: #111 !important; background: #fff !important;
        border-color: #ccc !important; }
    code, pre { background: #f4f4f4 !important; color: #222 !important;
                font-family: monospace !important; }
    h1,h2,h3 { color: #000 !important; }
    a { color: #1a56db !important; }
    blockquote { border-left: 3px solid #999 !important;
                 color: #555 !important; }
    table { border-collapse: collapse !important; }
    th, td { border: 1px solid #ccc !important; padding: 4px 8px !important; }
  `
  clone.appendChild(style)
  document.body.appendChild(clone)

  try {
    const canvas = await html2canvas(clone, {
      scale: 2,           // 2× for sharper text
      useCORS: true,
      backgroundColor: '#ffffff',
      logging: false,
    })

    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })

    const pageW = pdf.internal.pageSize.getWidth()
    const pageH = pdf.internal.pageSize.getHeight()
    const margin = 10   // mm

    const imgW = pageW - margin * 2
    const imgH = (canvas.height * imgW) / canvas.width

    let y = margin
    let remainingH = imgH

    // Paginate: slice the canvas image across pages
    while (remainingH > 0) {
      const sliceH = Math.min(remainingH, pageH - margin * 2)
      const srcY = Math.floor(((imgH - remainingH) / imgH) * canvas.height)
      const srcH = Math.min(canvas.height - srcY, Math.ceil((sliceH / imgH) * canvas.height))

      // Create a temporary canvas for this page slice
      const pageCanvas = document.createElement('canvas')
      pageCanvas.width  = canvas.width
      pageCanvas.height = srcH
      const ctx = pageCanvas.getContext('2d')!
      ctx.drawImage(canvas, 0, srcY, canvas.width, srcH, 0, 0, canvas.width, srcH)

      const sliceData = pageCanvas.toDataURL('image/png')
      pdf.addImage(sliceData, 'PNG', margin, y, imgW, sliceH)

      remainingH -= sliceH
      if (remainingH > 0) {
        pdf.addPage()
        y = margin
      }
    }

    pdf.save(filename)
  } finally {
    document.body.removeChild(clone)
  }
}
