use proc_macro::{TokenStream, TokenTree};

/// Include an item when any of the named reference snapshots exists.
#[proc_macro_attribute]
pub fn requires(args: TokenStream, item: TokenStream) -> TokenStream {
    select(args, item, true)
}

/// Include an ignored test when its reference snapshot is missing.
#[proc_macro_attribute]
pub fn missing(args: TokenStream, item: TokenStream) -> TokenStream {
    select(args, item, false)
}

fn select(args: TokenStream, item: TokenStream, present: bool) -> TokenStream {
    assert!(!args.is_empty(), "expected a reference snapshot name");

    let enabled = args
        .into_iter()
        .filter(|token| !matches!(token, TokenTree::Punct(punct) if punct.as_char() == ','))
        .map(|token| {
            let TokenTree::Ident(name) = token else {
                panic!("expected a reference snapshot name");
            };

            match name.to_string().as_str() {
                "has_ext_osu_refs" => cfg!(has_ext_osu_refs),
                "has_ext_acc_osu_refs" => cfg!(has_ext_acc_osu_refs),
                "has_ext_edge_osu_refs" => cfg!(has_ext_edge_osu_refs),
                "has_ext_mania_refs" => cfg!(has_ext_mania_refs),
                "has_ext_catch_refs" => cfg!(has_ext_catch_refs),
                "has_mass_osu_refs" => cfg!(has_mass_osu_refs),
                _ => panic!("unknown reference snapshot: {name}"),
            }
        })
        .fold(false, |any, available| any || available);

    if enabled == present {
        item
    } else {
        TokenStream::new()
    }
}
