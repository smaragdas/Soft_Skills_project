import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // Χτισίματα με σχετικά paths, δουλεύει τέλεια από οποιονδήποτε υποφάκελο (π.χ. /raters/)
  base: './',
  plugins: [react()],
})


