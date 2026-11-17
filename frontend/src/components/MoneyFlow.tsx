import { ResponsiveContainer, Sankey, Tooltip } from 'recharts'
import type { LinkProps, NodeProps } from 'recharts/types/chart/Sankey'
import { formatMoney, type FlowsData } from '../api'

const euros = (value: number) => formatMoney(Math.round(value)).replace(/,00$/, '')

interface NodePayload { name: string; color: string; value: number; depth: number }

/** Average monthly money flows as a Sankey: where it comes from, and where it goes. */
export default function MoneyFlow({ data }: { data: FlowsData }) {
  const sankeyData = { nodes: data.nodes.map((node) => ({ ...node })), links: data.links }

  const renderNode = (props: NodeProps) => {
    const { x, y, width, height } = props
    const payload = props.payload as unknown as NodePayload
    const depth = payload.depth
    const lastColumn = depth >= 3 || (depth === 2 && !data.links.some((link) => data.nodes[link.source]?.name === payload.name))
    const isSource = depth === 0
    const labelX = isSource ? x - 8 : x + width + 8
    const anchor = isSource ? 'end' : 'start'
    const tall = height > 22
    return (
      <g>
        <rect x={x} y={y} width={width} height={Math.max(height, 1)} fill={payload.color} rx={2} />
        <text x={labelX} y={y + height / 2 + (tall ? -2 : 4)} textAnchor={anchor} fontSize={12} fontWeight={depth === 2 || depth === 1 ? 700 : 500}
          fill="var(--text)" stroke="var(--surface)" strokeWidth={3} paintOrder="stroke">
          {payload.name}
        </text>
        {tall && (
          <text x={labelX} y={y + height / 2 + 12} textAnchor={anchor} fontSize={11} fill="var(--text-secondary)" stroke="var(--surface)" strokeWidth={3} paintOrder="stroke">
            {euros(payload.value)} / month
          </text>
        )}
        {!tall && lastColumn && (
          <text x={labelX + payload.name.length * 6.4 + 6} y={y + height / 2 + 4} textAnchor="start" fontSize={11} fill="var(--text-secondary)" stroke="var(--surface)" strokeWidth={3} paintOrder="stroke">
            {euros(payload.value)}
          </text>
        )}
      </g>
    )
  }

  const renderLink = (props: LinkProps) => {
    const { sourceX, targetX, sourceY, targetY, sourceControlX, targetControlX, linkWidth } = props
    const payload = props.payload as unknown as { source: NodePayload; target: NodePayload }
    const color = payload.target.name === 'Money in' ? payload.source.color : payload.target.color
    return (
      <path d={`M${sourceX},${sourceY} C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
        fill="none" stroke={color} strokeWidth={Math.max(linkWidth, 1)} strokeOpacity={0.32} />
    )
  }

  return (
    <div style={{ width: '100%', height: Math.max(420, Math.min(760, data.nodes.length * 21)) }}>
      <ResponsiveContainer width="100%" height="100%">
        <Sankey data={sankeyData} nodePadding={12} nodeWidth={12} node={renderNode} link={renderLink} margin={{ top: 8, bottom: 8, left: 130, right: 270 }} sort={false}>
          <Tooltip formatter={(value) => `${euros(Number(value))} / month`} contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }} />
        </Sankey>
      </ResponsiveContainer>
    </div>
  )
}
