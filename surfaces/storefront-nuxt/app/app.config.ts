export default defineAppConfig({
  ui: {
    colors: {
      primary: 'yellow',
      neutral: 'stone'
    },
    pageSection: {
      slots: {
        container: 'py-12 sm:py-16 lg:py-20 gap-6 sm:gap-10',
        headline: 'mb-2',
        title: 'text-2xl sm:text-3xl lg:text-4xl',
        description: 'text-sm sm:text-base',
        body: 'mt-8'
      },
      compoundVariants: [
        {
          orientation: 'vertical',
          title: true,
          class: {
            body: 'mt-8 sm:mt-10'
          }
        },
        {
          orientation: 'vertical',
          description: true,
          class: {
            body: 'mt-8 sm:mt-10'
          }
        },
        {
          orientation: 'vertical',
          body: true,
          class: {
            footer: 'mt-8 sm:mt-10'
          }
        }
      ]
    },
    pageHeader: {
      slots: {
        root: 'py-6 sm:py-8',
        title: 'text-3xl sm:text-4xl',
        description: 'text-base'
      }
    },
    pageCard: {
      slots: {
        title: 'text-base font-semibold',
        description: 'text-sm'
      }
    }
  }
})
