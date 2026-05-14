export default function HagiaSophia({ className }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1000 500"
      aria-hidden="true"
      className={className}
    >
      <defs>
        <clipPath id="sophiaClip">
          <rect x="0" y="0" width="1000" height="450" />
        </clipPath>
      </defs>
      <g fill="currentColor" clipPath="url(#sophiaClip)">
        <ellipse cx="500" cy="180" rx="140" ry="80" />
        <rect x="360" y="180" width="280" height="70" />
        <rect x="380" y="170" width="25" height="80" />
        <rect x="430" y="165" width="20" height="85" />
        <rect x="485" y="160" width="30" height="90" />
        <rect x="550" y="165" width="20" height="85" />
        <rect x="595" y="170" width="25" height="80" />
        <ellipse cx="360" cy="250" rx="100" ry="70" />
        <ellipse cx="640" cy="250" rx="100" ry="70" />
        <rect x="260" y="250" width="480" height="70" />
        <rect x="350" y="230" width="30" height="100" />
        <rect x="620" y="230" width="30" height="100" />
        <ellipse cx="260" cy="320" rx="70" ry="50" />
        <ellipse cx="740" cy="320" rx="70" ry="50" />
        <rect x="190" y="320" width="620" height="70" />
        <ellipse cx="190" cy="390" rx="50" ry="40" />
        <ellipse cx="810" cy="390" rx="50" ry="40" />
        <rect x="140" y="390" width="720" height="80" />
        <rect x="240" y="300" width="40" height="150" />
        <rect x="720" y="300" width="40" height="150" />
        <rect x="310" y="350" width="35" height="100" />
        <rect x="655" y="350" width="35" height="100" />
        <rect x="400" y="350" width="200" height="100" />
        <rect x="495" y="90" width="10" height="15" />
        <rect x="489" y="97" width="22" height="4" />
      </g>
    </svg>
  );
}
