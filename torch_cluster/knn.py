import torch
import scipy.spatial

if torch.cuda.is_available():
    import knn_cuda


def knn(x, y, k, batch_x=None, batch_y=None):
    """Finds for each element in `y` the `k` nearest points in `x`.

    Args:
        x (Tensor): D-dimensional point features.
        y (Tensor): D-dimensional point features.
        k (int): The number of neighbors.
        batch_x (LongTensor, optional): Vector that maps each point to its
            example identifier. If :obj:`None`, all points belong to the same
            example. If not :obj:`None`, points in the same example need to
            have contiguous memory layout and :obj:`batch` needs to be
            ascending. (default: :obj:`None`)
        batch_y (LongTensor, optional): See `batch_x` (default: :obj:`None`)

    :rtype: :class:`LongTensor`

    Examples::

        >>> x = torch.Tensor([[-1, -1], [-1, 1], [1, -1], [1, 1]])
        >>> batch_x = torch.tensor([0, 0, 0, 0])
        >>> y = torch.Tensor([[-1, 0], [1, 0]])
        >>> batch_x = torch.tensor([0, 0])
        >>> assign_index = knn(x, y, 2, batch_x, batch_y)
    """

    if batch_x is None:
        batch_x = x.new_zeros(x.size(0), dtype=torch.long)

    if batch_y is None:
        batch_y = y.new_zeros(y.size(0), dtype=torch.long)

    x = x.view(-1, 1) if x.dim() == 1 else x
    y = y.view(-1, 1) if y.dim() == 1 else y

    assert x.dim() == 2 and batch_x.dim() == 1
    assert y.dim() == 2 and batch_y.dim() == 1
    assert x.size(1) == y.size(1)
    assert x.size(0) == batch_x.size(0)
    assert y.size(0) == batch_y.size(0)

    if x.is_cuda:
        assign_index = knn_cuda.knn(x, y, k, batch_x, batch_y)
        return assign_index

    # Rescale x and y.
    min_xy = min(x.min().item(), y.min().item())
    x, y = x - min_xy, y - min_xy

    max_xy = max(x.max().item(), y.max().item())
    x, y, = x / max_xy, y / max_xy

    # Concat batch/features to ensure no cross-links between examples exist.
    x = torch.cat([x, 2 * x.size(1) * batch_x.view(-1, 1).to(x.dtype)], dim=-1)
    y = torch.cat([y, 2 * y.size(1) * batch_y.view(-1, 1).to(y.dtype)], dim=-1)

    tree = scipy.spatial.cKDTree(x)
    dist, col = tree.query(y, k=k, distance_upper_bound=x.size(1))
    dist, col = torch.tensor(dist), torch.tensor(col)
    row = torch.arange(col.size(0)).view(-1, 1).repeat(1, k)
    mask = 1 - torch.isinf(dist).view(-1)
    row, col = row.view(-1)[mask], col.view(-1)[mask]

    return torch.stack([row, col], dim=0)


def knn_graph(x, k, batch=None, loop=False):
    """Finds for each element in `x` the `k` nearest points.

    Args:
        x (Tensor): D-dimensional point features.
        k (int): The number of neighbors.
        batch (LongTensor, optional): Vector that maps each point to its
            example identifier. If :obj:`None`, all points belong to the same
            example. If not :obj:`None`, points in the same example need to
            have contiguous memory layout and :obj:`batch` needs to be
            ascending. (default: :obj:`None`)
        loop (bool, optional): If :obj:`True`, the graph will contain
            self-loops. (default: :obj:`False`)

    :rtype: :class:`LongTensor`

    Examples::

        >>> x = torch.Tensor([[-1, -1], [-1, 1], [1, -1], [1, 1]])
        >>> batch = torch.tensor([0, 0, 0, 0])
        >>> edge_index = knn_graph(x, k=2, batch=batch, loop=False)
    """

    edge_index = knn(x, x, k if loop else k + 1, batch, batch)
    if not loop:
        row, col = edge_index
        mask = row != col
        row, col = row[mask], col[mask]
        edge_index = torch.stack([row, col], dim=0)
    return edge_index
