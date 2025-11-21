import React from 'react'

type Props = {
  category: string
  setCategory: (v: string) => void
  qtype: string
  setQtype: (v: string) => void
  search: string
  setSearch: (v: string) => void
  hasLLM: string
  setHasLLM: (v: string) => void
}

export default function Filters(p: Props){
  return (
    <div className="panel controls">
      <select value={p.category} onChange={e=>p.setCategory(e.target.value)}>
        <option value="">All categories</option>
        <option>Communication</option>
        <option>Teamwork</option>
        <option>ProblemSolving</option>
        <option>Leadership</option>
      </select>
      <select value={p.qtype} onChange={e=>p.setQtype(e.target.value)}>
        <option value="">All types</option>
        <option value="open">Open</option>
        <option value="mc">Multiple Choice</option>
      </select>
      <select value={p.hasLLM} onChange={e=>p.setHasLLM(e.target.value)}>
        <option value="">LLM score: any</option>
        <option value="yes">Only with LLM</option>
        <option value="no">Only without LLM</option>
      </select>
      <input placeholder="Search prompt/answer/user…" value={p.search} onChange={e=>p.setSearch(e.target.value)} style={{minWidth:260}} />
    </div>
  )
}
