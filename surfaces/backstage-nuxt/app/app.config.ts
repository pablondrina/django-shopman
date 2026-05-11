export default defineAppConfig({
  ui: {
    colors: {
      primary: 'orange',
      neutral: 'neutral'
    },
    badge: {
      slots: {
        base: '!rounded-full'
      }
    },
    table: {
      slots: {
        th: 'px-3 py-2 text-sm text-highlighted text-left rtl:text-right font-semibold [&:has([role=checkbox])]:pe-0',
        td: 'px-3 py-2 text-sm text-muted whitespace-nowrap [&:has([role=checkbox])]:pe-0'
      }
    },
    card: {
      slots: {
        body: 'p-3 sm:p-4',
        header: 'p-3 sm:p-4',
        footer: 'p-3 sm:p-4'
      }
    }
  }
})
