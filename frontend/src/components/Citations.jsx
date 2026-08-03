import React from "react";

export default function Citations({ citations }) {
  if (!citations || !citations.length) return null;
  return (
    <div className="citations">
      <h4>Sources</h4>
      <ol>
        {citations.map((c) => (
          <li key={c.marker}>
            <span className="marker">[{c.marker}]</span>
            <span>
              {c.filename}
              {c.page != null && <span className="muted"> · p. {c.page}</span>}
              {c.section && <span className="muted"> · {c.section}</span>}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
