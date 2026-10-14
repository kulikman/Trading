interface GridProps {
  head: string[];
  children: React.ReactNode;
}

/** Таблица в стиле §2; на узком экране прокручивается внутри своего блока. */
export function Grid({ head, children }: GridProps): React.ReactElement {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {head.map((title) => (
              <th key={title}>{title}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

interface EmptyProps {
  text: string | null;
}

/** «Пусто — значит пусто» (§1): строка от бэкенда вместо таблицы с нулями. */
export function Empty({ text }: EmptyProps): React.ReactElement | null {
  return text ? <p className="muted">{text}</p> : null;
}
